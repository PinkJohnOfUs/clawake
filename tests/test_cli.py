import json
from pathlib import Path

from typer.testing import CliRunner

from clawake.cli import app
from clawake.services.systemd import CommandResult

runner = CliRunner()


class FakeSystemdService:
    def daemon_reload(self, execute: bool = False) -> CommandResult:
        return CommandResult(
            command=["systemctl", "--user", "daemon-reload"],
            return_code=0,
            stdout="ok",
            stderr="",
        )

    def restart(self, instance_name: str, execute: bool = False) -> CommandResult:
        return CommandResult(
            command=["systemctl", "--user", "restart", f"{instance_name}.service"],
            return_code=0,
            stdout="ok",
            stderr="",
        )

    def status(self, instance_name: str, execute: bool = False) -> CommandResult:
        return CommandResult(
            command=["systemctl", "--user", "status", f"{instance_name}.service"],
            return_code=0,
            stdout="active",
            stderr="",
        )

    def unit_name(self, instance_name: str) -> str:
        return f"{instance_name}.service"


def test_validate_command() -> None:
    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/product.yml"))])
    assert result.exit_code == 0
    assert "is valid for cluster" in result.stdout


def test_apply_dry_run(tmp_path: Path) -> None:
    target = tmp_path / "quadlet"
    result = runner.invoke(
        app,
        [
            "apply",
            "--config",
            str(Path("examples/staff/product.yml")),
            "--target",
            str(target),
            "--output",
            str(tmp_path / "rendered"),
        ],
    )
    assert result.exit_code == 0
    assert "DRY RUN apply complete" in result.stdout
    assert not (target / "openclaw-product-owner.container").exists()


def test_apply_execute(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    monkeypatch.setattr(cli, "SystemdService", FakeSystemdService)

    target = tmp_path / "quadlet"
    result = runner.invoke(
        app,
        [
            "apply",
            "--config",
            str(Path("examples/staff/product.yml")),
            "--target",
            str(target),
            "--output",
            str(tmp_path / "rendered"),
            "--execute",
        ],
    )
    assert result.exit_code == 0
    assert (target / "openclaw-product-owner.container").exists()
    assert (target / "openclaw-developer.container").exists()


def test_status_cluster_json(monkeypatch: object) -> None:
    from clawake import cli

    monkeypatch.setattr(cli, "SystemdService", FakeSystemdService)
    result = runner.invoke(
        app,
        [
            "status-cluster",
            "--config",
            str(Path("examples/staff/product.yml")),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["cluster"] == "single-host-mvp"
    assert len(payload["instances"]) == 2
    assert {instance["role"] for instance in payload["instances"]} == {
        "product_owner",
        "developer",
    }
