from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ClusterSpec(BaseModel):
    name: str
    mode: Literal["single_host"] = "single_host"
    primary_host: str
    description: str | None = None


class HostSpec(BaseModel):
    name: str
    quadlet_root: str = "~/.config/containers/systemd"
    ssh_target: str | None = None


class ImageSpec(BaseModel):
    repository: str
    tag: str
    digest: str | None = None
    known_good_digest: str | None = None


class PortSpec(BaseModel):
    bind_address: str = "127.0.0.1"
    host_port: int = Field(ge=1, le=65535)
    container_port: int = Field(ge=1, le=65535)
    protocol: Literal["tcp", "udp"] = "tcp"


class MountSpec(BaseModel):
    source: str
    target: str
    read_only: bool = False


class HealthSpec(BaseModel):
    path: str = "/health"
    interval_seconds: int = 30
    timeout_seconds: int = 5
    retries: int = 3


class UpdatePolicy(BaseModel):
    channel: str = "stable"
    strategy: str = "manual"
    auto_apply: bool = False


class BackupPolicy(BaseModel):
    enabled: bool = True
    pre_mutation: bool = True
    retention: int = 5
    paths: list[str] = Field(default_factory=list)


class GatewayRuntimeSpec(BaseModel):
    enabled: bool = False
    bind: Literal["loopback", "lan", "tailnet", "auto", "custom"] = "lan"
    gateway_container_port: int = Field(default=18789, ge=1, le=65535)
    bridge_container_port: int = Field(default=18790, ge=1, le=65535)


class DashboardMeta(BaseModel):
    friendly_name: str
    owner: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class AutoOnboardSpec(BaseModel):
    enabled: bool = True
    openclaw_config: dict[str, Any] = Field(default_factory=dict)
    required_env: list[str] = Field(default_factory=list)


class InstanceSpec(BaseModel):
    name: str
    host: str
    role: Literal["product_owner", "developer"]
    profile: Literal["public", "internal"]
    workspace_path: str
    config_path: str
    state_path: str
    service_scope: Literal["user"] = "user"
    quadlet_path: str
    container_name: str
    image: ImageSpec
    ports: list[PortSpec] = Field(default_factory=list)
    mounts: list[MountSpec] = Field(default_factory=list)
    env_files: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    public_url: str | None = None
    health: HealthSpec = Field(default_factory=HealthSpec)
    update_policy: UpdatePolicy = Field(default_factory=UpdatePolicy)
    backup_policy: BackupPolicy = Field(default_factory=BackupPolicy)
    gateway_runtime: GatewayRuntimeSpec = Field(default_factory=GatewayRuntimeSpec)
    auto_onboard: AutoOnboardSpec | None = None
    dashboard: DashboardMeta

    @model_validator(mode="after")
    def ensure_backup_defaults(self) -> InstanceSpec:
        if not self.backup_policy.paths:
            self.backup_policy.paths = [
                self.workspace_path,
                self.config_path,
                self.state_path,
            ]
        return self


class Inventory(BaseModel):
    version: int = 1
    cluster: ClusterSpec
    hosts: list[HostSpec]
    instances: list[InstanceSpec]

    @model_validator(mode="after")
    def validate_inventory(self) -> Inventory:
        def _expand_path(raw_path: str) -> str:
            expanded = os.path.expandvars(raw_path)
            expanded = expanded.replace("${workspaceFolder}", os.environ.get("CLAWAKE_WORKSPACE_ROOT", ""))
            return str(Path(expanded).expanduser())

        def _validate_safe_absolute_path(label: str, raw_path: str) -> str:
            path = Path(_expand_path(raw_path))
            if not path.is_absolute():
                raise ValueError(f"{label} must be an absolute path: '{raw_path}'")
            normalized = str(path)
            if "//" in normalized:
                raise ValueError(f"{label} must not contain repeated slashes: '{raw_path}'")
            parts = set(path.parts)
            if "." in parts or ".." in parts:
                raise ValueError(f"{label} must not contain dot segments: '{raw_path}'")
            return normalized

        host_names = {host.name for host in self.hosts}
        if len(host_names) != len(self.hosts):
            raise ValueError("Duplicate host names are not allowed")

        if len(self.hosts) != 1:
            raise ValueError("single_host mode requires exactly one host")

        if self.cluster.primary_host not in host_names:
            raise ValueError(
                f"cluster.primary_host '{self.cluster.primary_host}' does not match any host"
            )

        instance_names: set[str] = set()
        used_ports: dict[tuple[str, str, int, str], str] = {}
        used_paths: dict[str, tuple[str, str]] = {}

        for instance in self.instances:
            if instance.host not in host_names:
                raise ValueError(
                    f"Instance '{instance.name}' references unknown host '{instance.host}'"
                )
            if instance.name in instance_names:
                raise ValueError(f"Duplicate instance name '{instance.name}'")
            instance_names.add(instance.name)

            _validate_safe_absolute_path(
                f"instances[{instance.name}].workspace_path",
                instance.workspace_path,
            )
            _validate_safe_absolute_path(
                f"instances[{instance.name}].config_path",
                instance.config_path,
            )
            _validate_safe_absolute_path(
                f"instances[{instance.name}].state_path",
                instance.state_path,
            )
            for env_file in instance.env_files:
                _validate_safe_absolute_path(
                    f"instances[{instance.name}].env_files",
                    env_file,
                )
            for mount in instance.mounts:
                source = _validate_safe_absolute_path(
                    f"instances[{instance.name}].mounts.source",
                    mount.source,
                )
                if ":" in source:
                    raise ValueError(
                        f"instances[{instance.name}].mounts.source must not contain ':'"
                    )
                _validate_safe_absolute_path(
                    f"instances[{instance.name}].mounts.target",
                    mount.target,
                )

            if instance.gateway_runtime.enabled:
                expected = {
                    instance.gateway_runtime.gateway_container_port,
                    instance.gateway_runtime.bridge_container_port,
                }
                actual = {port.container_port for port in instance.ports}
                if not expected.issubset(actual):
                    raise ValueError(
                        f"Instance '{instance.name}' enables gateway_runtime but is missing "
                        f"container ports {sorted(expected)}"
                    )

            for port in instance.ports:
                port_key = (instance.host, port.bind_address, port.host_port, port.protocol)
                if port_key in used_ports:
                    raise ValueError(
                        f"Port collision on host {instance.host} "
                        f"{port.bind_address}:{port.host_port} "
                        f"between {used_ports[port_key]} and {instance.name}"
                    )
                used_ports[port_key] = instance.name

            storage_paths = {
                "workspace_path": instance.workspace_path,
                "config_path": instance.config_path,
                "state_path": instance.state_path,
            }
            for boundary, raw_path in storage_paths.items():
                normalized = _expand_path(raw_path)
                existing = used_paths.get(normalized)
                if existing is not None:
                    raise ValueError(
                        f"Path collision for '{normalized}' between "
                        f"{existing[0]}.{existing[1]} and {instance.name}.{boundary}"
                    )
                used_paths[normalized] = (instance.name, boundary)

        return self


def _expand_string_values(value: object, env: Mapping[str, str]) -> object:
    def _expand_with_env(text: str) -> str:
        pattern = re.compile(r"\$(\w+)|\$\{([^}]+)\}")

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1) or match.group(2)
            return env.get(key, match.group(0))

        return pattern.sub(_replace, text)

    if isinstance(value, str):
        return _expand_with_env(value)
    if isinstance(value, list):
        return [_expand_string_values(item, env) for item in value]
    if isinstance(value, dict):
        return {
            key: _expand_string_values(item, env)
            for key, item in value.items()
        }
    return value


def load_inventory(path: str | Path) -> Inventory:
    inventory_path = Path(path)
    data = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Inventory file must contain a YAML mapping")

    workspace_root = inventory_path.resolve().parents[2] if len(inventory_path.resolve().parents) >= 3 else inventory_path.resolve().parent
    expansion_env = {
        **os.environ,
        "workspaceFolder": os.environ.get("CLAWAKE_WORKSPACE_ROOT", str(workspace_root)),
        "CLAWAKE_WORKSPACE_ROOT": os.environ.get("CLAWAKE_WORKSPACE_ROOT", str(workspace_root)),
    }
    expanded_data = _expand_string_values(data, expansion_env)
    return Inventory.model_validate(expanded_data)
