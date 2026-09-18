from pathlib import Path
from types import SimpleNamespace

from clawake.config import DashboardMeta, ImageSpec, InstanceSpec
from clawake.services.runtime_upgrade import (
    doctor_command,
    is_browser_image,
    runtime_version_from_tag,
    verify_runtime,
)


def _instance(tmp_path: Path) -> InstanceSpec:
    workspace = tmp_path / "workspace"
    role = tmp_path / "role"
    env_file = tmp_path / "member.env"
    workspace.mkdir()
    role.mkdir()
    env_file.write_text("TOKEN=secret\n", encoding="utf-8")
    return InstanceSpec(
        name="one",
        host="local",
        role="developer",
        workspace_path=str(workspace),
        team_definition_path=str(role),
        quadlet_path="one.container",
        container_name="one",
        image=ImageSpec(repository="ghcr.io/openclaw/openclaw", tag="old"),
        env_files=[str(env_file)],
        dashboard=DashboardMeta(friendly_name="One"),
    )


def test_doctor_command_reuses_member_runtime_boundaries(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    instance.dns_servers = ["192.168.2.1"]
    target = ImageSpec(repository="ghcr.io/openclaw/openclaw", tag="2026.8.2", digest="sha256:new")

    command = doctor_command(instance, target)

    env_index = command.index("--env-file")
    assert command[env_index : env_index + 2] == ["--env-file", instance.env_files[0]]
    assert f"{instance.workspace_path}:/workspace" in command
    assert f"{instance.workspace_path}/.openclaw:/home/node/.openclaw" in command
    assert command[command.index("--dns") : command.index("--dns") + 2] == [
        "--dns",
        "192.168.2.1",
    ]
    assert command[-5:] == ["openclaw", "doctor", "--fix", "--non-interactive", "--yes"]


def test_verify_runtime_accepts_podman_normalized_digest_reference(
    monkeypatch: object, tmp_path: Path
) -> None:
    instance = _instance(tmp_path)
    target = ImageSpec(repository="ghcr.io/openclaw/openclaw", tag="2026.8.2", digest="sha256:new")
    results = iter(
        [
            SimpleNamespace(returncode=0, stdout="OpenClaw 2026.8.2\n", stderr=""),
            SimpleNamespace(
                returncode=0,
                stdout="ghcr.io/openclaw/openclaw@sha256:new\n",
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(
        "clawake.services.runtime_upgrade.subprocess.run", lambda *args, **kwargs: next(results)
    )

    result = verify_runtime(instance, target)

    assert result.healthy is True
    assert result.version == "OpenClaw 2026.8.2"


def test_runtime_version_from_official_browser_image_tag() -> None:
    assert runtime_version_from_tag("2026.8.2-browser") == "2026.8.2"
    assert runtime_version_from_tag("2026.8.2-browser-amd64") == "2026.8.2"
    assert runtime_version_from_tag("2026.8.2") == "2026.8.2"


def test_browser_image_gets_writable_openclaw_cache_tmpfs(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    target = ImageSpec(repository="example.invalid/openclaw", tag="2026.8.2-browser")

    command = doctor_command(instance, target)

    assert is_browser_image(target) is True
    assert command[4] == "--volume"
    assert command[5].endswith("/.openclaw/cache/openclaw-1000:/home/node/.cache/openclaw-1000")
