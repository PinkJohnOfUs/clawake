import hashlib
from pathlib import Path

import pytest

from clawake.config import InstanceSpec, PluginSpec
from clawake.services.plugins import (
    artifact_digest,
    plugin_commands,
    sync_plugin,
    verify_plugin,
)


def _plugin(path: Path, digest: str) -> PluginSpec:
    return PluginSpec(
        id="example-plugin",
        artifact_path=str(path),
        sha256=digest,
        enabled=True,
        custom_ui=True,
        config={"publicOrigin": "http://127.0.0.1:18789"},
    )


def test_verify_plugin_accepts_exact_digest_and_rejects_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "plugin.tgz"
    artifact.write_bytes(b"reviewed plugin")
    digest = f"sha256:{hashlib.sha256(artifact.read_bytes()).hexdigest()}"
    plugin = _plugin(artifact, digest)

    assert artifact_digest(artifact) == digest
    assert verify_plugin(plugin) == digest

    artifact.write_bytes(b"tampered plugin")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_plugin(plugin)


def test_plugin_commands_use_container_mount_and_structured_arguments(tmp_path: Path) -> None:
    artifact = tmp_path / "plugin.tgz"
    artifact.write_bytes(b"plugin")
    plugin = _plugin(artifact, f"sha256:{hashlib.sha256(artifact.read_bytes()).hexdigest()}")
    instance = InstanceSpec.model_construct(container_name="one")

    commands = plugin_commands(instance, plugin)

    assert commands[0] == [
        "podman",
        "exec",
        "one",
        "openclaw",
        "plugins",
        "install",
        "--force",
        "--accept-capabilities",
        "/opt/clawake/plugins/example-plugin.tgz",
    ]
    assert commands[2][-1] == '{"publicOrigin":"http://127.0.0.1:18789"}'
    assert commands[3][-2:] == ["gateway.controlUi.experimental.customPlugins", "true"]


def test_npm_plugin_requires_exact_version_and_integrity() -> None:
    plugin = PluginSpec(
        id="whatsapp",
        npm_spec="@openclaw/whatsapp@2026.9.2",
        integrity="sha512-dGVzdA==",
    )
    instance = InstanceSpec.model_construct(container_name="one")

    assert verify_plugin(plugin) == "sha512-dGVzdA=="
    assert plugin_commands(instance, plugin)[0] == [
        "podman",
        "exec",
        "one",
        "openclaw",
        "plugins",
        "install",
        "--force",
        "--accept-capabilities",
        "npm:@openclaw/whatsapp@2026.9.2",
        "--pin",
    ]
    assert not any(command[-2].endswith(".config") for command in plugin_commands(instance, plugin))

    with pytest.raises(ValueError, match="exact package version"):
        PluginSpec(
            id="whatsapp",
            npm_spec="@openclaw/whatsapp@latest",
            integrity="sha512-dGVzdA==",
        )


def test_sync_verifies_installed_npm_integrity(monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = PluginSpec(
        id="whatsapp",
        npm_spec="@openclaw/whatsapp@2026.9.2",
        integrity="sha512-dGVzdA==",
    )
    instance = InstanceSpec.model_construct(container_name="one")

    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str = "") -> None:
            self.stdout = stdout

    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> Result:
        calls.append(command)
        if "inspect" in command:
            return Result(
                '{"plugin":{"id":"whatsapp"},"install":'
                '{"resolvedSpec":"@openclaw/whatsapp@2026.9.2",'
                '"integrity":"sha512-dGVzdA=="}}'
            )
        return Result()

    monkeypatch.setattr("clawake.services.plugins.subprocess.run", run)

    sync_plugin(instance, plugin, execute=True)

    assert any("inspect" in command for command in calls)


def test_plugin_rejects_mixed_or_incomplete_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one source"):
        PluginSpec(
            id="mixed",
            artifact_path=str(tmp_path / "plugin.tgz"),
            sha256=f"sha256:{'0' * 64}",
            npm_spec="example@1.2.3",
            integrity="sha512-dGVzdA==",
        )
    with pytest.raises(ValueError, match="require artifact_path and sha256"):
        PluginSpec(id="incomplete", artifact_path=str(tmp_path / "plugin.tgz"))


def test_sync_rejects_mounted_artifact_with_different_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "plugin.tgz"
    artifact.write_bytes(b"plugin")
    plugin = _plugin(artifact, f"sha256:{hashlib.sha256(artifact.read_bytes()).hexdigest()}")
    instance = InstanceSpec.model_construct(container_name="one")

    class Result:
        returncode = 0
        stdout = f"{'0' * 64}  {plugin.container_path}\n"
        stderr = ""

    monkeypatch.setattr("clawake.services.plugins.subprocess.run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="Mounted plugin.*digest mismatch"):
        sync_plugin(instance, plugin, execute=True)
