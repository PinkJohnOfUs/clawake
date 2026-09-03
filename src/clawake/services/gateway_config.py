from __future__ import annotations

import json
import os
from pathlib import Path

from clawake.config import InstanceSpec

_LOOPBACK_ADDRESSES = {"127.0.0.1", "::1", "localhost"}


def _format_origin_host(address: str) -> str:
    if ":" in address and not address.startswith("["):
        return f"[{address}]"
    return address


def local_control_ui_origins(instance: InstanceSpec) -> list[str]:
    """Return browser origins Clawake can derive from the gateway port mapping."""
    origins: list[str] = []
    gateway_port = instance.gateway_runtime.gateway_container_port
    for port in instance.ports:
        if port.protocol != "tcp" or port.container_port != gateway_port:
            continue
        host = _format_origin_host(port.bind_address)
        origins.append(f"http://{host}:{port.host_port}")
        if port.bind_address in _LOOPBACK_ADDRESSES:
            origins.append(f"http://localhost:{port.host_port}")
    return list(dict.fromkeys(origins))


def ensure_control_ui_config(instance: InstanceSpec) -> tuple[Path, bool]:
    """Merge inferred local Control UI settings into OpenClaw's persisted config."""
    config_path = Path(instance.workspace_path).expanduser() / ".openclaw" / "openclaw.json"
    origins = local_control_ui_origins(instance)
    if not instance.gateway_runtime.enabled or not origins:
        return config_path, False

    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid OpenClaw config '{config_path}': {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"OpenClaw config '{config_path}' must contain a JSON object")
    else:
        payload = {}

    gateway = payload.setdefault("gateway", {})
    if not isinstance(gateway, dict):
        raise ValueError(f"OpenClaw config '{config_path}': gateway must be an object")
    control_ui = gateway.setdefault("controlUi", {})
    if not isinstance(control_ui, dict):
        raise ValueError(f"OpenClaw config '{config_path}': gateway.controlUi must be an object")

    existing_origins = control_ui.get("allowedOrigins", [])
    if not isinstance(existing_origins, list) or not all(
        isinstance(origin, str) for origin in existing_origins
    ):
        raise ValueError(
            f"OpenClaw config '{config_path}': gateway.controlUi.allowedOrigins "
            "must be a string array"
        )

    changed = False
    merged_origins = list(dict.fromkeys([*existing_origins, *origins]))
    if merged_origins != existing_origins:
        control_ui["allowedOrigins"] = merged_origins
        changed = True

    gateway_bindings = [
        port.bind_address
        for port in instance.ports
        if port.protocol == "tcp"
        and port.container_port == instance.gateway_runtime.gateway_container_port
    ]
    local_http_only = bool(gateway_bindings) and all(
        address in _LOOPBACK_ADDRESSES for address in gateway_bindings
    )
    if local_http_only and "allowInsecureAuth" not in control_ui:
        # OpenClaw otherwise rejects token authentication from its HTTP Control UI.
        # This is only enabled when the published gateway is loopback-only.
        control_ui["allowInsecureAuth"] = True
        changed = True

    if not changed:
        return config_path, False

    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(".json.clawake-tmp")
    temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(config_path)
    return config_path, True
