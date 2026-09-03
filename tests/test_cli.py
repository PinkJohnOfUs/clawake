import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from clawake.cli import app
from clawake.services.systemd import CommandResult

runner = CliRunner()


def _write_inventory(
    tmp_path: Path,
    *,
    quadlet_root: Path | None = None,
    env_content: str = "OPENCLAW_GATEWAY_TOKEN=sample-token\n",
) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    team_definition = tmp_path / "team.yml"
    env_file = tmp_path / "instance.env"
    inventory_file = tmp_path / "inventory.yml"

    workspace.mkdir(parents=True, exist_ok=True)
    team_definition.write_text("team: sample\n", encoding="utf-8")
    env_file.write_text(env_content, encoding="utf-8")

    data = {
        "version": 1,
        "cluster": {
            "name": "c",
            "mode": "single_host",
            "primary_host": "h",
        },
        "hosts": [
            {
                "name": "h",
                "quadlet_root": str(quadlet_root or (tmp_path / "quadlet-target")),
            }
        ],
        "instances": [
            {
                "name": "one",
                "host": "h",
                "role": "developer",
                "workspace_path": str(workspace),
                "team_definition_path": str(team_definition),
                "quadlet_path": "one.container",
                "container_name": "one",
                "image": {
                    "repository": "ghcr.io/openclaw/openclaw",
                    "tag": "2026.6.5",
                },
                "ports": [
                    {
                        "bind_address": "127.0.0.1",
                        "host_port": 18789,
                        "container_port": 18789,
                        "protocol": "tcp",
                    },
                    {
                        "bind_address": "127.0.0.1",
                        "host_port": 18790,
                        "container_port": 18790,
                        "protocol": "tcp",
                    },
                ],
                "env_files": [str(env_file)],
                "gateway_runtime": {
                    "enabled": True,
                    "bind": "loopback",
                    "gateway_container_port": 18789,
                    "bridge_container_port": 18790,
                },
                "dashboard": {"friendly_name": "One"},
            }
        ],
    }
    inventory_file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return inventory_file, env_file, workspace


def test_diagnose_dashboard_json_reports_expected_fields(tmp_path: Path) -> None:
    cfg, _env_file, _workspace = _write_inventory(tmp_path)

    result = runner.invoke(app, ["diagnose-dashboard", "--config", str(cfg), "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["cluster"] == "c"
    instance = payload["instances"][0]
    assert instance["instance"] == "one"
    assert instance["dashboard_url"] == "http://127.0.0.1:18789/"
    assert instance["token_present"] is True


def test_diagnose_dashboard_show_token_url_includes_auth_fragment(tmp_path: Path) -> None:
    cfg, _env_file, _workspace = _write_inventory(tmp_path)

    result = runner.invoke(
        app,
        [
            "diagnose-dashboard",
            "--config",
            str(cfg),
            "--show-token-url",
        ],
    )

    assert result.exit_code == 0
    assert "auth_url:" in result.output
    assert "#token=sample-token" in result.output


def test_onboard_member_dry_run_uses_managed_workspace(tmp_path: Path) -> None:
    cfg, _env_file, _workspace = _write_inventory(tmp_path)

    result = runner.invoke(
        app,
        ["onboard-member", "--config", str(cfg), "--member", "one"],
    )

    assert result.exit_code == 0
    assert "podman exec --interactive --tty one openclaw onboard" in result.output
    assert "--workspace /workspace" in result.output
    assert "--skip-bootstrap" in result.output
    assert "--no-install-daemon" in result.output
    assert "DRY RUN onboard-member complete" in result.output


def test_setup_quadlets_dry_run_succeeds(tmp_path: Path) -> None:
    cfg, _env_file, _workspace = _write_inventory(tmp_path)

    result = runner.invoke(app, ["setup-quadlets", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "DRY RUN setup-quadlets complete" in result.output


def test_setup_quadlets_execute_deploys_files(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    class RecordingSystemdService:
        daemon_reload_calls = 0
        restart_calls = 0

        def daemon_reload(self, execute: bool = False) -> CommandResult:
            RecordingSystemdService.daemon_reload_calls += 1
            return CommandResult(["systemctl", "--user", "daemon-reload"], 0, "ok", "")

        def restart(self, instance_name: str, execute: bool = False) -> CommandResult:
            RecordingSystemdService.restart_calls += 1
            return CommandResult(
                ["systemctl", "--user", "restart", f"{instance_name}.service"],
                0,
                "ok",
                "",
            )

    quadlet_root = tmp_path / "quadlets"
    cfg, _env_file, _workspace = _write_inventory(tmp_path, quadlet_root=quadlet_root)
    monkeypatch.setattr(cli, "SystemdService", RecordingSystemdService)

    result = runner.invoke(app, ["setup-quadlets", "--config", str(cfg), "--execute"])

    assert result.exit_code == 0
    assert (quadlet_root / "one.container").is_file()
    assert (quadlet_root / "one.network").is_file()
    assert (quadlet_root / "one-state.volume").is_file()
    assert (_workspace / ".openclaw").is_dir()
    openclaw_config = json.loads(
        (_workspace / ".openclaw" / "openclaw.json").read_text(encoding="utf-8")
    )
    assert openclaw_config["gateway"]["controlUi"] == {
        "allowedOrigins": [
            "http://127.0.0.1:18789",
            "http://localhost:18789",
        ],
        "allowInsecureAuth": True,
    }
    assert RecordingSystemdService.daemon_reload_calls == 1
    assert RecordingSystemdService.restart_calls == 1


def test_setup_quadlets_execute_starts_unchanged_service(
    monkeypatch: object, tmp_path: Path
) -> None:
    from clawake import cli

    class RecordingSystemdService:
        restart_calls = 0

        def daemon_reload(self, execute: bool = False) -> CommandResult:
            return CommandResult(["systemctl", "--user", "daemon-reload"], 0, "ok", "")

        def restart(self, instance_name: str, execute: bool = False) -> CommandResult:
            RecordingSystemdService.restart_calls += 1
            return CommandResult(
                ["systemctl", "--user", "restart", f"{instance_name}.service"],
                0,
                "ok",
                "",
            )

    quadlet_root = tmp_path / "quadlets"
    cfg, _env_file, _workspace = _write_inventory(tmp_path, quadlet_root=quadlet_root)
    monkeypatch.setattr(cli, "SystemdService", RecordingSystemdService)

    first = runner.invoke(app, ["setup-quadlets", "--config", str(cfg), "--execute"])
    second = runner.invoke(app, ["setup-quadlets", "--config", str(cfg), "--execute"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "ensuring selected services are running" in second.output
    assert RecordingSystemdService.restart_calls == 2


def test_restart_quadlets_execute_propagates_failures(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    class FailingSystemdService:
        def restart(self, instance_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(
                ["systemctl", "--user", "restart", f"{instance_name}.service"],
                1,
                "",
                "failed",
            )

    cfg, _env_file, _workspace = _write_inventory(tmp_path)
    monkeypatch.setattr(cli, "SystemdService", FailingSystemdService)

    result = runner.invoke(app, ["restart-quadlets", "--config", str(cfg), "--execute"])

    assert result.exit_code == 1


def test_status_quadlets_json_healthy(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    class HealthySystemdService:
        def status(self, instance_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(
                ["systemctl", "--user", "status", f"{instance_name}.service"],
                0,
                "active",
                "",
            )

        def logs(
            self, instance_name: str, lines: int = 100, execute: bool = False
        ) -> CommandResult:
            return CommandResult(["journalctl"], 0, "", "")

        def unit_name(self, instance_name: str) -> str:
            return f"{instance_name}.service"

    cfg, _env_file, _workspace = _write_inventory(tmp_path)
    monkeypatch.setattr(cli, "SystemdService", HealthySystemdService)

    result = runner.invoke(app, ["status-quadlets", "--config", str(cfg), "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["instances"][0]["state"] == "healthy"
    assert payload["instances"][0]["unit"] == "one.service"


def test_status_quadlets_text_prints_diagnostic_cause(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    class FailedSystemdService:
        def status(self, instance_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(
                ["systemctl", "--user", "status", f"{instance_name}.service"],
                3,
                "Active: failed (Result: exit-code)",
                "",
            )

        def logs(
            self, instance_name: str, lines: int = 100, execute: bool = False
        ) -> CommandResult:
            return CommandResult(["journalctl"], 0, "EnvironmentFile missing", "")

        def unit_name(self, instance_name: str) -> str:
            return f"{instance_name}.service"

    cfg, _env_file, _workspace = _write_inventory(tmp_path)
    monkeypatch.setattr(cli, "SystemdService", FailedSystemdService)

    result = runner.invoke(app, ["status-quadlets", "--config", str(cfg), "--format", "text"])

    assert result.exit_code == 1
    assert "state=failed rc=3" in result.output
    assert "cause: EnvironmentFile missing" in result.output


def test_teardown_quadlets_dry_run_succeeds(tmp_path: Path) -> None:
    cfg, _env_file, _workspace = _write_inventory(tmp_path)

    result = runner.invoke(app, ["teardown-quadlets", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "DRY RUN teardown-quadlets complete" in result.output
