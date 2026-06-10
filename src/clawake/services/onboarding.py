from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clawake.config import InstanceSpec

_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REQUIRED_PREFIX = "$ENV:"
_OPTIONAL_PREFIX = "$ENV?:"


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
            return env.get(key)
        if value.startswith(_REQUIRED_PREFIX):
            key = value[len(_REQUIRED_PREFIX) :]
            if key not in env:
                missing_required_env.add(key)
                return None
            return env[key]
        return value

    if isinstance(value, list):
        return [_resolve_template_value(item, env, missing_required_env) for item in value]

    if isinstance(value, dict):
        return {
            key: _resolve_template_value(item, env, missing_required_env)
            for key, item in value.items()
        }

    return value


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

    for key in instance.auto_onboard.required_env:
        if key not in env:
            missing_required_env.add(key)

    guardrails = [
        f"Use openclaw --profile {instance.profile} for CLI commands inside this instance"
    ]
    provider = env.get("OPENCLAW_MODEL_PROVIDER", "openai").strip().lower()
    if provider == "openai" and not env.get("OPENAI_API_KEY"):
        guardrails.append(
            "Model auth for OpenAI is not configured via env. "
            f"Run: openclaw --profile {instance.profile} models auth login --provider openai --device-code"
        )

    target = Path(instance.config_path).expanduser() / "openclaw.json"
    backup = Path(instance.config_path).expanduser() / "openclaw.json.last-good"
    return AutoOnboardPlan(
        instance=instance.name,
        target_path=target,
        backup_path=backup,
        config=rendered_config,
        missing_required_env=sorted(missing_required_env),
        guardrails=guardrails,
    )


def write_auto_onboard_config(plan: AutoOnboardPlan, execute: bool = False) -> None:
    if not execute:
        return

    plan.target_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.target_path.exists():
        shutil.copy2(plan.target_path, plan.backup_path)

    plan.target_path.write_text(
        json.dumps(plan.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
