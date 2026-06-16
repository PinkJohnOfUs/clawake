from __future__ import annotations

import copy
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from clawake.config import InstanceSpec

_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REQUIRED_PREFIX = "$ENV:"
_OPTIONAL_PREFIX = "$ENV?:"
_UNSET = object()


def _is_sensitive_env_key(key: str) -> bool:
    upper_key = key.upper()
    sensitive_tokens = ("TOKEN", "API_KEY", "SECRET", "PASSWORD", "PASSWD")
    return any(token in upper_key for token in sensitive_tokens)


def _is_env_reference(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith(_REQUIRED_PREFIX) or value.startswith(_OPTIONAL_PREFIX)


@dataclass
class AutoOnboardPlan:
    instance: str
    target_path: Path
    backup_path: Path
    config: dict[str, Any]
    missing_required_env: list[str]
    guardrails: list[str] = field(default_factory=list)


class AutoOnboardError(ValueError):
    pass


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise AutoOnboardError(f"EnvironmentFile missing: {path}")
    if not path.is_file():
        raise AutoOnboardError(f"EnvironmentFile is not a regular file: {path}")

    env: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise AutoOnboardError(
                f"invalid env entry in {path}:{line_number} (expected KEY=VALUE)"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_PATTERN.fullmatch(key):
            raise AutoOnboardError(f"invalid env key in {path}:{line_number} ('{key}')")
        env[key] = value
    return env


def _collect_instance_env(instance: InstanceSpec) -> dict[str, str]:
    merged: dict[str, str] = {}
    for raw_path in instance.env_files:
        env_path = Path(raw_path).expanduser()
        merged.update(_load_env_file(env_path))
    return merged


def _resolve_template_value(
    value: Any,
    env: dict[str, str],
    missing_required_env: set[str],
) -> Any:
    if isinstance(value, str):
        if value.startswith(_OPTIONAL_PREFIX):
            key = value[len(_OPTIONAL_PREFIX) :]
            if key not in env:
                return value
            if _is_sensitive_env_key(key):
                return value
            return env[key]
        if value.startswith(_REQUIRED_PREFIX):
            key = value[len(_REQUIRED_PREFIX) :]
            if key not in env:
                missing_required_env.add(key)
                return None
            if _is_sensitive_env_key(key):
                return value
            return env[key]
        return value

    if isinstance(value, list):
        return [
            resolved
            for item in value
            if (resolved := _resolve_template_value(item, env, missing_required_env)) is not _UNSET
        ]

    if isinstance(value, dict):
        return {
            key: resolved
            for key, item in value.items()
            if (resolved := _resolve_template_value(item, env, missing_required_env)) is not _UNSET
        }

    return value


def _load_existing_config(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _deep_merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = copy.deepcopy(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_config(existing, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _normalize_openclaw_config(config: dict[str, Any]) -> dict[str, Any]:
    channels = config.get("channels")
    if not isinstance(channels, dict):
        return config

    discord = channels.get("discord")
    if not isinstance(discord, dict):
        return config

    server_id = discord.pop("server_id", _UNSET)
    channel_id = discord.pop("channel_id", _UNSET)

    if server_id is _UNSET and channel_id is _UNSET:
        return config

    if (
        isinstance(server_id, str)
        and isinstance(channel_id, str)
        and not _is_env_reference(server_id)
        and not _is_env_reference(channel_id)
    ):
        guilds = discord.setdefault("guilds", {})
        if isinstance(guilds, dict):
            guild = guilds.setdefault(server_id, {})
            if isinstance(guild, dict):
                guild_channels = guild.setdefault("channels", {})
                if isinstance(guild_channels, dict):
                    guild_channels.setdefault(
                        channel_id,
                        {"enabled": True, "requireMention": False},
                    )

    return config


def build_auto_onboard_plan(instance: InstanceSpec) -> AutoOnboardPlan:
    if not instance.auto_onboard or not instance.auto_onboard.enabled:
        raise AutoOnboardError(
            f"Instance '{instance.name}' does not define auto_onboard settings"
        )
    if not instance.auto_onboard.openclaw_config:
        raise AutoOnboardError(
            f"Instance '{instance.name}' has empty auto_onboard.openclaw_config"
        )

    env = _collect_instance_env(instance)

    missing_required_env: set[str] = set()
    rendered_config = _resolve_template_value(
        instance.auto_onboard.openclaw_config,
        env,
        missing_required_env,
    )
    rendered_config = _normalize_openclaw_config(rendered_config)

    for key in instance.auto_onboard.required_env:
        if key not in env:
            missing_required_env.add(key)

    guardrails = [
        "Use openclaw commands directly inside this instance"
    ]
    provider = env.get("OPENCLAW_MODEL_PROVIDER", "openai").strip().lower()
    if provider == "openai" and not env.get("OPENAI_API_KEY"):
        guardrails.append(
            "Model auth for OpenAI is not configured via env. "
            "Run: openclaw models auth login --provider openai --device-code"
        )

    runtime_dir = Path(instance.workspace_path).expanduser() / ".openclaw"
    target = runtime_dir / "openclaw.json"
    backup = runtime_dir / "openclaw.json.last-good"
    return AutoOnboardPlan(
        instance=instance.name,
        target_path=target,
        backup_path=backup,
        config=rendered_config,
        missing_required_env=sorted(missing_required_env),
        guardrails=guardrails,
    )


def _template_root() -> Path:
    return Path(__file__).resolve().parents[3] / "templates"


def _render_openclaw_json(config: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_template_root())),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("openclaw/openclaw.json.j2")
    rendered_json = json.dumps(config, indent=2)
    return template.render(rendered_json=rendered_json).strip() + "\n"


def write_auto_onboard_config(plan: AutoOnboardPlan, execute: bool = False) -> None:
    if not execute:
        return

    plan.target_path.parent.mkdir(parents=True, exist_ok=True)
    existing_config = _load_existing_config(plan.target_path)
    final_config = _deep_merge_config(existing_config, plan.config)
    final_config = _normalize_openclaw_config(final_config)
    if plan.target_path.exists():
        shutil.copy2(plan.target_path, plan.backup_path)

    plan.target_path.write_text(_render_openclaw_json(final_config), encoding="utf-8")


def auto_onboard_would_change(plan: AutoOnboardPlan) -> bool:
    existing_config = _load_existing_config(plan.target_path)
    final_config = _deep_merge_config(existing_config, plan.config)
    final_config = _normalize_openclaw_config(final_config)
    return final_config != existing_config
