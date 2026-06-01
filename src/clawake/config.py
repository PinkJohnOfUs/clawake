from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


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


class DashboardMeta(BaseModel):
    friendly_name: str
    owner: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class InstanceSpec(BaseModel):
    name: str
    host: str
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
    dashboard: DashboardMeta


class Inventory(BaseModel):
    version: int = 1
    hosts: list[HostSpec]
    instances: list[InstanceSpec]

    @model_validator(mode="after")
    def validate_inventory(self) -> Inventory:
        host_names = {host.name for host in self.hosts}
        if len(host_names) != len(self.hosts):
            raise ValueError("Duplicate host names are not allowed")

        instance_names: set[str] = set()
        used_ports: dict[tuple[str, str, int], str] = {}

        for instance in self.instances:
            if instance.host not in host_names:
                raise ValueError(
                    f"Instance '{instance.name}' references unknown host '{instance.host}'"
                )
            if instance.name in instance_names:
                raise ValueError(f"Duplicate instance name '{instance.name}'")
            instance_names.add(instance.name)

            for port in instance.ports:
                key = (instance.host, port.bind_address, port.host_port)
                if key in used_ports:
                    raise ValueError(
                        f"Port collision on host {instance.host} "
                        f"{port.bind_address}:{port.host_port} "
                        f"between {used_ports[key]} and {instance.name}"
                    )
                used_ports[key] = instance.name

        return self


def load_inventory(path: str | Path) -> Inventory:
    inventory_path = Path(path)
    data = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    return Inventory.model_validate(data)
