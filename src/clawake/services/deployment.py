"""Side-effect-free deployment planning and explicit artifact application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clawake.config import InstanceSpec, Inventory
from clawake.services.render import render_instance_assets


@dataclass(frozen=True)
class ArtifactChange:
    member: str
    role: str
    destination: Path
    content: str


def plan_deployment(
    inventory: Inventory, instances: list[InstanceSpec], template_root: Path
) -> list[ArtifactChange]:
    """Render desired state in memory and compare it with installed artifacts."""
    hosts = {host.name: host for host in inventory.hosts}
    changes = []
    for instance in instances:
        root = Path(hosts[instance.host].quadlet_root).expanduser()
        for relative, content in render_instance_assets(instance, template_root).items():
            destination = root / relative
            current = destination.read_text(encoding="utf-8") if destination.exists() else None
            if current != content:
                changes.append(ArtifactChange(instance.name, instance.role, destination, content))
    return changes


def apply_artifacts(changes: list[ArtifactChange]) -> list[Path]:
    """Write a reviewed plan. The caller owns runtime preparation and reloads."""
    deployed = []
    for change in changes:
        change.destination.parent.mkdir(parents=True, exist_ok=True)
        change.destination.write_text(change.content, encoding="utf-8")
        deployed.append(change.destination)
    return deployed
