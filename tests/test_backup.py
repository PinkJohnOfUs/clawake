import tarfile
from pathlib import Path

from clawake.config import BackupPolicy, DashboardMeta, ImageSpec, InstanceSpec
from clawake.services.backup import backup_instance, prune_backups


def _instance_with_paths(workspace: Path, team_definition_path: Path) -> InstanceSpec:
    return InstanceSpec(
        name="one",
        host="h",
        role="developer",
        workspace_path=str(workspace),
        team_definition_path=str(team_definition_path),
        quadlet_path="one.container",
        container_name="one",
        image=ImageSpec(repository="ghcr.io/openclaw/openclaw", tag="2026.6.5"),
        backup_policy=BackupPolicy(enabled=True, pre_mutation=True),
        dashboard=DashboardMeta(friendly_name="One"),
    )


def test_backup_instance_skips_unreadable_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    team_definition = tmp_path / "role"
    output_dir = tmp_path / "backups"

    workspace.mkdir(parents=True, exist_ok=True)
    team_definition.mkdir(parents=True, exist_ok=True)

    readable = team_definition / "readable.txt"
    readable.write_text("ok\n", encoding="utf-8")

    unreadable = team_definition / "openclaw.json"
    unreadable.write_text("{}\n", encoding="utf-8")
    unreadable.chmod(0)

    instance = _instance_with_paths(workspace, team_definition)

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
    team_definition = tmp_path / "role"
    output_dir = tmp_path / "backups"

    workspace.mkdir(parents=True, exist_ok=True)
    team_definition.mkdir(parents=True, exist_ok=True)

    instance = _instance_with_paths(workspace, team_definition)
    archive = backup_instance(instance, output_dir=output_dir, execute=False)

    assert not archive.exists()
    assert archive.parent == output_dir


def test_backup_instance_skips_legacy_workspace_runtime_tree(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    team_definition = tmp_path / "role"
    output_dir = tmp_path / "backups"

    workspace.mkdir(parents=True, exist_ok=True)
    team_definition.mkdir(parents=True, exist_ok=True)

    legacy_runtime = workspace / ".clawake" / "state"
    legacy_runtime.mkdir(parents=True, exist_ok=True)
    (legacy_runtime / "openclaw.json").write_text('{"legacy":true}\n', encoding="utf-8")
    (workspace / "README.txt").write_text("workspace data\n", encoding="utf-8")

    instance = _instance_with_paths(workspace, team_definition)
    archive = backup_instance(instance, output_dir=output_dir, execute=True)

    with tarfile.open(archive, "r:gz") as tar:
        members = [member.name for member in tar.getmembers()]

    assert any(name.endswith("/README.txt") for name in members)
    assert not any("/.clawake/" in name for name in members)


def test_prune_backups_retains_newest_matching_files(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    paths = [backups / f"one-{number}.tar.gz" for number in range(3)]
    for path in paths:
        path.write_text(path.name, encoding="utf-8")

    removed = prune_backups(backups, "one-", retention=2)

    assert removed == [paths[0]]
    assert not paths[0].exists()
    assert paths[1].exists()
    assert paths[2].exists()
