import tarfile
from pathlib import Path

from clawake.config import BackupPolicy, DashboardMeta, ImageSpec, InstanceSpec
from clawake.services.backup import backup_instance


def _instance_with_paths(workspace: Path, config_path: Path, state_path: Path) -> InstanceSpec:
    return InstanceSpec(
        name="one",
        host="h",
        role="developer",
        profile="internal",
        workspace_path=str(workspace),
        config_path=str(config_path),
        state_path=str(state_path),
        quadlet_path="one.container",
        container_name="one",
        image=ImageSpec(repository="ghcr.io/openclaw/openclaw", tag="2026.6.5"),
        backup_policy=BackupPolicy(enabled=True, pre_mutation=True),
        dashboard=DashboardMeta(friendly_name="One"),
    )


def test_backup_instance_skips_unreadable_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    config_dir = tmp_path / "config"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "backups"

    workspace.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    readable = state_dir / "readable.txt"
    readable.write_text("ok\n", encoding="utf-8")

    unreadable = state_dir / "openclaw.json"
    unreadable.write_text("{}\n", encoding="utf-8")
    unreadable.chmod(0)

    instance = _instance_with_paths(workspace, config_dir, state_dir)

    try:
        archive = backup_instance(instance, output_dir=output_dir, execute=True)
    finally:
        unreadable.chmod(0o600)

    assert archive.exists()

    with tarfile.open(archive, "r:gz") as tar:
        members = [member.name for member in tar.getmembers()]

    assert any(name.endswith("/readable.txt") for name in members)
    assert not any(name.endswith("/openclaw.json") for name in members)


def test_backup_instance_dry_run_does_not_create_archive(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    config_dir = tmp_path / "config"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "backups"

    workspace.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    instance = _instance_with_paths(workspace, config_dir, state_dir)
    archive = backup_instance(instance, output_dir=output_dir, execute=False)

    assert not archive.exists()
    assert archive.parent == output_dir


def test_backup_instance_skips_legacy_workspace_runtime_tree(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    config_dir = tmp_path / "config"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "backups"

    workspace.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    legacy_runtime = workspace / ".clawake" / "state"
    legacy_runtime.mkdir(parents=True, exist_ok=True)
    (legacy_runtime / "openclaw.json").write_text('{"legacy":true}\n', encoding="utf-8")
    (workspace / "README.txt").write_text("workspace data\n", encoding="utf-8")

    instance = _instance_with_paths(workspace, config_dir, state_dir)
    archive = backup_instance(instance, output_dir=output_dir, execute=True)

    with tarfile.open(archive, "r:gz") as tar:
        members = [member.name for member in tar.getmembers()]

    assert any(name.endswith("/README.txt") for name in members)
    assert not any("/.clawake/" in name for name in members)
