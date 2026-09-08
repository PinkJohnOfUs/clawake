from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from clawake.config import InstanceSpec, PluginSpec


@dataclass(frozen=True)
class PluginSyncResult:
    plugin_id: str
    digest: str
    commands: list[list[str]]


def artifact_digest(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def verify_plugin(plugin: PluginSpec) -> str:
    path = Path(plugin.artifact_path)
    if not path.is_file():
        raise ValueError(f"Plugin artifact does not exist: {path}")
    actual = artifact_digest(path)
    if actual != plugin.sha256:
        raise ValueError(
            f"Plugin '{plugin.id}' digest mismatch: expected {plugin.sha256}, got {actual}"
        )
    return actual


def plugin_commands(instance: InstanceSpec, plugin: PluginSpec) -> list[list[str]]:
    commands = [
        [
            "podman", "exec", instance.container_name, "openclaw", "plugins", "install",
            "--force", "--accept-capabilities", plugin.container_path,
        ],
        [
            "podman", "exec", instance.container_name, "openclaw", "config", "set",
            f"plugins.entries.{plugin.id}.enabled", "true" if plugin.enabled else "false",
        ],
        [
            "podman", "exec", instance.container_name, "openclaw", "config", "set",
            f"plugins.entries.{plugin.id}.config",
            json.dumps(plugin.config, separators=(",", ":"), sort_keys=True),
        ],
    ]
    if plugin.custom_ui:
        commands.append(
            [
                "podman", "exec", instance.container_name, "openclaw", "config", "set",
                "gateway.controlUi.experimental.customPlugins", "true",
            ]
        )
    return commands


def _verify_mounted_artifact(instance: InstanceSpec, plugin: PluginSpec) -> None:
    command = ["podman", "exec", instance.container_name, "sha256sum", plugin.container_path]
    process = subprocess.run(command, check=False, capture_output=True, text=True)
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise RuntimeError(f"Cannot verify mounted plugin '{plugin.id}': {detail}")
    mounted_hash = process.stdout.strip().split(maxsplit=1)[0]
    mounted_digest = f"sha256:{mounted_hash}"
    if mounted_digest != plugin.sha256:
        raise RuntimeError(
            f"Mounted plugin '{plugin.id}' digest mismatch: expected {plugin.sha256}, "
            f"got {mounted_digest}. Run clawake setup --execute before syncing."
        )


def sync_plugin(
    instance: InstanceSpec, plugin: PluginSpec, execute: bool = False
) -> PluginSyncResult:
    digest = verify_plugin(plugin)
    commands = plugin_commands(instance, plugin)
    if execute:
        _verify_mounted_artifact(instance, plugin)
        for command in commands:
            process = subprocess.run(command, check=False, capture_output=True, text=True)
            if process.returncode != 0:
                detail = process.stderr.strip() or process.stdout.strip()
                raise RuntimeError(f"Plugin command failed ({' '.join(command)}): {detail}")
    return PluginSyncResult(plugin.id, digest, commands)
