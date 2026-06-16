import json
import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from clawake.cli import app
from clawake.services.systemd import CommandResult
from clawake.services.image_check import ImageCheckError

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

    def logs(self, instance_name: str, lines: int = 100, execute: bool = False) -> CommandResult:
        return CommandResult(
            command=["journalctl", "--user-unit", f"{instance_name}.service", "-n", str(lines)],
            return_code=0,
            stdout="log output",
            stderr="",
        )

    def unit_name(self, instance_name: str) -> str:
        return f"{instance_name}.service"


def test_validate_command(monkeypatch: object) -> None:
    from clawake import cli

    # Positive case: image check is a no-op (registry not required in unit tests)
    monkeypatch.setattr(cli, "check_image_availability", lambda _: None)

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/team.yml"))])
    assert result.exit_code == 0
    assert "is valid for cluster" in result.stdout


def test_validate_missing_env_file(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    monkeypatch.setattr(cli, "check_image_availability", lambda _: None)

    cfg = tmp_path / "missing-env.yml"
    cfg.write_text(
        """
version: 1
cluster:
  name: c
  mode: single_host
  primary_host: a
hosts:
  - name: a
instances:
  - name: one
    host: a
    role: developer
    workspace_path: /tmp/one/workspace
    config_path: /tmp/one/config
    state_path: /tmp/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    env_files:
      - /tmp/does-not-exist.env
    dashboard: {friendly_name: One}
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["validate", "--config", str(cfg)])

    assert result.exit_code != 0
    assert "EnvironmentFile missing" in result.output


def test_validate_invalid_env_file_content(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    monkeypatch.setattr(cli, "check_image_availability", lambda _: None)

    env_file = tmp_path / "invalid.env"
    env_file.write_text("BAD LINE\nGOOD_KEY=value\n", encoding="utf-8")

    cfg = tmp_path / "invalid-env.yml"
    cfg.write_text(
        f"""
version: 1
cluster:
  name: c
  mode: single_host
  primary_host: a
hosts:
  - name: a
instances:
  - name: one
    host: a
    role: developer
    workspace_path: /tmp/one/workspace
    config_path: /tmp/one/config
    state_path: /tmp/one/state
    quadlet_path: one.container
    container_name: one
    image: {{repository: ghcr.io/x, tag: "1"}}
    env_files:
      - {env_file}
    dashboard: {{friendly_name: One}}
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["validate", "--config", str(cfg)])

    assert result.exit_code != 0
    assert "expected KEY=VALUE" in result.output


# ---------------------------------------------------------------------------
# Negative test cases for validate: image unavailable
# ---------------------------------------------------------------------------

def _make_image_check_raiser(reason: str, hint: str):
    """Return a fake check_image_availability that always raises ImageCheckError."""
    def _check(image_spec):
        ref = f"{image_spec.repository}:{image_spec.tag}"
        if image_spec.digest:
            ref = f"{image_spec.repository}@{image_spec.digest}"
        raise ImageCheckError(image_ref=ref, reason=reason, hint=hint)
    return _check


def test_validate_image_not_found(monkeypatch: object) -> None:
    """validate exits non-zero and surfaces registry 404 with a clear fix hint."""
    from clawake import cli

    monkeypatch.setattr(
        cli,
        "check_image_availability",
        _make_image_check_raiser(
            reason="manifest unknown: manifest unknown",
            hint="Check that the image tag and digest are correct and the image exists in the registry.",
        ),
    )

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/team.yml"))])

    assert result.exit_code != 0
    # The image reference should appear so the operator knows which image failed
    assert "ghcr.io/openclaw/openclaw" in result.output
    # The raw registry error must be visible
    assert "manifest unknown" in result.output
    # An actionable fix hint must be present
    assert "Check that the image tag" in result.output


def test_validate_image_auth_error(monkeypatch: object) -> None:
    """validate exits non-zero and explains that OpenClaw images are public."""
    from clawake import cli

    monkeypatch.setattr(
        cli,
        "check_image_availability",
        _make_image_check_raiser(
            reason="unauthorized: access to the requested resource is not authorized",
            hint=(
                "The registry refused access to this image reference. OpenClaw images are public and do not require "
                "podman login; verify the repository, tag, and digest, and confirm that the image is actually "
                "published in ghcr.io."
            ),
        ),
    )

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/team.yml"))])

    assert result.exit_code != 0
    assert "unauthorized" in result.output.lower()
    assert "openclaw images are public" in result.output.lower()
    assert "do not require podman login" in result.output.lower()
    assert "verify the repository, tag, and digest" in result.output.lower()
    assert "published in ghcr.io" in result.output.lower()
    assert "https://github.com/openclaw/openclaw/pkgs/container/openclaw" in result.output


def test_validate_image_network_error(monkeypatch: object) -> None:
    """validate exits non-zero and directs the operator to check network connectivity."""
    from clawake import cli

    monkeypatch.setattr(
        cli,
        "check_image_availability",
        _make_image_check_raiser(
            reason="dial tcp: connection refused",
            hint="Network error. Check connectivity to the registry and any proxy or firewall settings.",
        ),
    )

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/team.yml"))])

    assert result.exit_code != 0
    assert "connection refused" in result.output.lower()
    assert "network" in result.output.lower()


def test_validate_image_digest_mismatch(monkeypatch: object) -> None:
    """validate exits non-zero and tells the operator to reconcile the digest."""
    from clawake import cli

    monkeypatch.setattr(
        cli,
        "check_image_availability",
        _make_image_check_raiser(
            reason="manifest digest mismatch: expected sha256:deadbeef, got sha256:cafebabe",
            hint=(
                "The image digest in the config does not match the registry. "
                "Update 'digest' in product.yml or verify the image has not been replaced."
            ),
        ),
    )

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/team.yml"))])

    assert result.exit_code != 0
    assert "digest" in result.output.lower()
    assert "product.yml" in result.output


def test_validate_image_errors_reported_per_instance(monkeypatch: object) -> None:
    """All failing instances are reported before validate exits; not fail-fast on first."""
    from clawake import cli

    call_count = 0

    def _count_and_raise(image_spec):
        nonlocal call_count
        call_count += 1
        raise ImageCheckError(
            image_ref=f"{image_spec.repository}:{image_spec.tag}",
            reason="manifest unknown: manifest unknown",
            hint="Check that the image tag and digest are correct.",
        )

    monkeypatch.setattr(cli, "check_image_availability", _count_and_raise)

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/team.yml"))])

    # Both instances in product.yml must have been checked
    assert call_count == 2
    assert result.exit_code != 0

def test_apply_dry_run(tmp_path: Path) -> None:
    target = tmp_path / "quadlet"
    result = runner.invoke(
        app,
        [
            "apply",
            "--config",
            str(Path("examples/staff/team.yml")),
            "--target",
            str(target),
            "--output",
            str(tmp_path / "rendered"),
        ],
    )
    assert result.exit_code == 0
    assert "DRY RUN apply complete" in result.stdout
    assert not (target / "excalibot-product-owner.container").exists()


def test_apply_execute(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    monkeypatch.setattr(cli, "SystemdService", FakeSystemdService)
    monkeypatch.setattr(
        cli,
        "backup_instance",
        lambda *_args, **_kwargs: Path(".backups/instances/test.tar.gz"),
    )

    target = tmp_path / "quadlet"
    result = runner.invoke(
        app,
        [
            "apply",
            "--config",
            str(Path("examples/staff/team.yml")),
            "--target",
            str(target),
            "--output",
            str(tmp_path / "rendered"),
            "--execute",
        ],
    )
    assert result.exit_code == 0
    assert (target / "excalibot-product-owner.container").exists()
    assert (target / "excalibot-developer.container").exists()


def test_apply_execute_no_changes_still_reloads(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    class RecordingSystemdService:
        daemon_reload_calls = 0
        restart_calls = 0

        def daemon_reload(self, execute: bool = False) -> CommandResult:
            RecordingSystemdService.daemon_reload_calls += 1
            return CommandResult(
                command=["systemctl", "--user", "daemon-reload"],
                return_code=0,
                stdout="ok",
                stderr="",
            )

        def restart(self, instance_name: str, execute: bool = False) -> CommandResult:
            RecordingSystemdService.restart_calls += 1
            return CommandResult(
                command=["systemctl", "--user", "restart", f"{instance_name}.service"],
                return_code=0,
                stdout="ok",
                stderr="",
            )

    monkeypatch.setattr(cli, "SystemdService", RecordingSystemdService)

    target = tmp_path / "quadlet"
    output = tmp_path / "rendered"

    render_result = runner.invoke(
        app,
        [
            "render",
            "--config",
            str(Path("examples/staff/team.yml")),
            "--output",
            str(output),
        ],
    )
    assert render_result.exit_code == 0

    target.mkdir(parents=True, exist_ok=True)
    for rendered_file in output.glob("*.container"):
        shutil.copy2(rendered_file, target / rendered_file.name)

    result = runner.invoke(
        app,
        [
            "apply",
            "--config",
            str(Path("examples/staff/team.yml")),
            "--target",
            str(target),
            "--output",
            str(output),
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert RecordingSystemdService.daemon_reload_calls == 1
    assert RecordingSystemdService.restart_calls == 0
    assert "No rendered changes detected; daemon-reload completed." in result.output


def test_apply_execute_repairs_auto_onboard_config_without_quadlet_changes(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    from clawake import cli

    class RecordingSystemdService:
        daemon_reload_calls = 0
        restart_calls = 0

        def daemon_reload(self, execute: bool = False) -> CommandResult:
            RecordingSystemdService.daemon_reload_calls += 1
            return CommandResult(
                command=["systemctl", "--user", "daemon-reload"],
                return_code=0,
                stdout="ok",
                stderr="",
            )

        def restart(self, instance_name: str, execute: bool = False) -> CommandResult:
            RecordingSystemdService.restart_calls += 1
            return CommandResult(
                command=["systemctl", "--user", "restart", f"{instance_name}.service"],
                return_code=0,
                stdout="ok",
                stderr="",
            )

    monkeypatch.setattr(cli, "SystemdService", RecordingSystemdService)

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CLAWAKE_RUNTIME_ROOT", str(runtime_root))

    env_file = tmp_path / "instance.env"
    env_file.write_text(
        "OPENCLAW_GATEWAY_BIND=local\nOPENCLAW_GATEWAY_TOKEN=test-token\n",
        encoding="utf-8",
    )

    config_file = tmp_path / "inventory.yml"
    config_data = {
        "version": 1,
        "cluster": {
            "name": "c",
            "mode": "single_host",
            "primary_host": "h",
        },
        "hosts": [{"name": "h"}],
        "instances": [
            {
                "name": "one",
                "host": "h",
                "role": "developer",
                "workspace_path": str(workspace),
                "quadlet_path": "one.container",
                "container_name": "one",
                "image": {"repository": "ghcr.io/openclaw/openclaw", "tag": "2026.6.5"},
                "env_files": [str(env_file)],
                "auto_onboard": {
                    "required_env": ["OPENCLAW_GATEWAY_BIND", "OPENCLAW_GATEWAY_TOKEN"],
                    "openclaw_config": {
                        "gateway": {
                            "mode": "$ENV:OPENCLAW_GATEWAY_BIND",
                            "auth": {"token": "$ENV:OPENCLAW_GATEWAY_TOKEN"},
                        }
                    },
                },
                "dashboard": {"friendly_name": "One"},
            }
        ],
    }
    config_file.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    output = tmp_path / "rendered"
    target = tmp_path / "target"
    render_result = runner.invoke(
        app,
        [
            "render",
            "--config",
            str(config_file),
            "--output",
            str(output),
        ],
    )
    assert render_result.exit_code == 0

    target.mkdir(parents=True, exist_ok=True)
    for rendered_file in output.glob("*.container"):
        shutil.copy2(rendered_file, target / rendered_file.name)

    runtime_state = runtime_root / "one" / "state"
    runtime_state.mkdir(parents=True, exist_ok=True)
    (runtime_state / "openclaw.json").write_text('{"gateway": {"auth": {"token": "test-token"}}}\n', encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "apply",
            "--config",
            str(config_file),
            "--target",
            str(target),
            "--output",
            str(output),
            "--execute",
        ],
    )

    assert result.exit_code == 0
    repaired = json.loads((runtime_state / "openclaw.json").read_text(encoding="utf-8"))
    assert repaired["gateway"]["mode"] == "local"
    assert RecordingSystemdService.daemon_reload_calls == 1
    assert RecordingSystemdService.restart_calls == 1
    assert "Auto-onboard repaired runtime config for one" in result.output


def test_apply_execute_repairs_auto_onboard_when_value_mismatch(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    from clawake import cli

    class RecordingSystemdService:
        daemon_reload_calls = 0
        restart_calls = 0

        def daemon_reload(self, execute: bool = False) -> CommandResult:
            RecordingSystemdService.daemon_reload_calls += 1
            return CommandResult(
                command=["systemctl", "--user", "daemon-reload"],
                return_code=0,
                stdout="ok",
                stderr="",
            )

        def restart(self, instance_name: str, execute: bool = False) -> CommandResult:
            RecordingSystemdService.restart_calls += 1
            return CommandResult(
                command=["systemctl", "--user", "restart", f"{instance_name}.service"],
                return_code=0,
                stdout="ok",
                stderr="",
            )

    monkeypatch.setattr(cli, "SystemdService", RecordingSystemdService)

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CLAWAKE_RUNTIME_ROOT", str(runtime_root))

    env_file = tmp_path / "instance.env"
    env_file.write_text(
        "OPENCLAW_GATEWAY_BIND=local\nOPENCLAW_GATEWAY_TOKEN=test-token\n",
        encoding="utf-8",
    )

    config_file = tmp_path / "inventory.yml"
    config_data = {
        "version": 1,
        "cluster": {
            "name": "c",
            "mode": "single_host",
            "primary_host": "h",
        },
        "hosts": [{"name": "h"}],
        "instances": [
            {
                "name": "one",
                "host": "h",
                "role": "developer",
                "workspace_path": str(workspace),
                "quadlet_path": "one.container",
                "container_name": "one",
                "image": {"repository": "ghcr.io/openclaw/openclaw", "tag": "2026.6.5"},
                "env_files": [str(env_file)],
                "auto_onboard": {
                    "required_env": ["OPENCLAW_GATEWAY_BIND", "OPENCLAW_GATEWAY_TOKEN"],
                    "openclaw_config": {
                        "gateway": {
                            "mode": "$ENV:OPENCLAW_GATEWAY_BIND",
                            "auth": {"token": "$ENV:OPENCLAW_GATEWAY_TOKEN"},
                        }
                    },
                },
                "dashboard": {"friendly_name": "One"},
            }
        ],
    }
    config_file.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    output = tmp_path / "rendered"
    target = tmp_path / "target"
    render_result = runner.invoke(
        app,
        [
            "render",
            "--config",
            str(config_file),
            "--output",
            str(output),
        ],
    )
    assert render_result.exit_code == 0

    target.mkdir(parents=True, exist_ok=True)
    for rendered_file in output.glob("*.container"):
        shutil.copy2(rendered_file, target / rendered_file.name)

    runtime_state = runtime_root / "one" / "state"
    runtime_state.mkdir(parents=True, exist_ok=True)
    (runtime_state / "openclaw.json").write_text(
        '{"gateway": {"mode": "remote", "auth": {"token": "test-token"}}}\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "apply",
            "--config",
            str(config_file),
            "--target",
            str(target),
            "--output",
            str(output),
            "--execute",
        ],
    )

    assert result.exit_code == 0
    repaired = json.loads((runtime_state / "openclaw.json").read_text(encoding="utf-8"))
    assert repaired["gateway"]["mode"] == "local"
    assert RecordingSystemdService.daemon_reload_calls == 1
    assert RecordingSystemdService.restart_calls == 1
    assert "Auto-onboard repaired runtime config for one" in result.output


def test_apply_execute_prepares_runtime_mount_paths(monkeypatch: object, tmp_path: Path) -> None:
        from clawake import cli

        monkeypatch.setattr(cli, "SystemdService", FakeSystemdService)

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        config_path = tmp_path / "runtime" / "config"
        state_path = tmp_path / "runtime" / "state"
        env_file = tmp_path / "instance.env"
        env_file.write_text("OPENCLAW_MODEL_PROVIDER=openai\n", encoding="utf-8")

        config_file = tmp_path / "inventory.yml"
        config_data = {
                "version": 1,
                "cluster": {
                        "name": "c",
                        "mode": "single_host",
                        "primary_host": "h",
                },
                "hosts": [{"name": "h"}],
                "instances": [
                        {
                                "name": "one",
                                "host": "h",
                                "role": "developer",
                                "workspace_path": str(workspace),
                                "config_path": str(config_path),
                                "state_path": str(state_path),
                                "quadlet_path": "one.container",
                                "container_name": "one",
                                "image": {"repository": "ghcr.io/openclaw/openclaw", "tag": "2026.6.5"},
                                "env_files": [str(env_file)],
                                "dashboard": {"friendly_name": "One"},
                        }
                ],
        }
        config_file.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

        target = tmp_path / "quadlet"
        output = tmp_path / "rendered"
        result = runner.invoke(
                app,
                [
                        "apply",
                        "--config",
                        str(config_file),
                        "--target",
                        str(target),
                        "--output",
                        str(output),
                        "--execute",
                ],
        )

        assert result.exit_code == 0
        assert config_path.is_dir()
        assert state_path.is_dir()
        assert (state_path / "workspace-internal").is_dir()
        assert (state_path / "openclaw.json").is_file()


def test_apply_execute_fails_when_workspace_missing(monkeypatch: object, tmp_path: Path) -> None:
        from clawake import cli

        monkeypatch.setattr(cli, "SystemdService", FakeSystemdService)

        missing_workspace = tmp_path / "workspace-missing"
        config_path = tmp_path / "runtime" / "config"
        state_path = tmp_path / "runtime" / "state"
        env_file = tmp_path / "instance.env"
        env_file.write_text("OPENCLAW_MODEL_PROVIDER=openai\n", encoding="utf-8")

        config_file = tmp_path / "inventory.yml"
        config_data = {
                "version": 1,
                "cluster": {
                        "name": "c",
                        "mode": "single_host",
                        "primary_host": "h",
                },
                "hosts": [{"name": "h"}],
                "instances": [
                        {
                                "name": "one",
                                "host": "h",
                                "role": "developer",
                                "workspace_path": str(missing_workspace),
                                "config_path": str(config_path),
                                "state_path": str(state_path),
                                "quadlet_path": "one.container",
                                "container_name": "one",
                                "image": {"repository": "ghcr.io/openclaw/openclaw", "tag": "2026.6.5"},
                                "env_files": [str(env_file)],
                                "dashboard": {"friendly_name": "One"},
                        }
                ],
        }
        config_file.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

        target = tmp_path / "quadlet"
        output = tmp_path / "rendered"
        result = runner.invoke(
                app,
                [
                        "apply",
                        "--config",
                        str(config_file),
                        "--target",
                        str(target),
                        "--output",
                        str(output),
                        "--execute",
                ],
        )

        assert result.exit_code != 0
        assert "Workspace path missing or not a directory" in result.output


def test_apply_execute_repairs_owner_mismatched_state_file(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    monkeypatch.setattr(cli, "SystemdService", FakeSystemdService)
    monkeypatch.setattr(
        cli,
        "backup_instance",
        lambda *_args, **_kwargs: Path(".backups/instances/test.tar.gz"),
    )

    workspace = tmp_path / "workspace"
    config_path = tmp_path / "runtime" / "config"
    state_path = tmp_path / "runtime" / "state"
    env_file = tmp_path / "instance.env"

    workspace.mkdir(parents=True, exist_ok=True)
    config_path.mkdir(parents=True, exist_ok=True)
    state_path.mkdir(parents=True, exist_ok=True)
    env_file.write_text("OPENCLAW_MODEL_PROVIDER=openai\n", encoding="utf-8")
    (config_path / "openclaw.json").write_text("{}\n", encoding="utf-8")

    state_file = state_path / "openclaw.json"
    state_file.write_text('{"token":"abc"}\n', encoding="utf-8")

    monkeypatch.setattr(cli.os, "getuid", lambda: 100000)
    monkeypatch.setattr(cli.os, "getgid", lambda: 100000)

    config_file = tmp_path / "inventory.yml"
    config_data = {
        "version": 1,
        "cluster": {
            "name": "c",
            "mode": "single_host",
            "primary_host": "h",
        },
        "hosts": [{"name": "h"}],
        "instances": [
            {
                "name": "one",
                "host": "h",
                "role": "developer",
                "workspace_path": str(workspace),
                "config_path": str(config_path),
                "state_path": str(state_path),
                "quadlet_path": "one.container",
                "container_name": "one",
                "image": {"repository": "ghcr.io/openclaw/openclaw", "tag": "2026.6.5"},
                "env_files": [str(env_file)],
                "dashboard": {"friendly_name": "One"},
            }
        ],
    }
    config_file.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    target = tmp_path / "quadlet"
    output = tmp_path / "rendered"
    result = runner.invoke(
        app,
        [
            "apply",
            "--config",
            str(config_file),
            "--target",
            str(target),
            "--output",
            str(output),
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert state_file.exists()
    assert state_file.read_text(encoding="utf-8") == '{"token":"abc"}\n'
    assert "Repaired runtime state file" in result.output
    assert "owner" in result.output


def test_status_inactive_service_prints_recent_logs(monkeypatch: object) -> None:
    from clawake import cli

    class DiagnosticSystemdService:
        def status(self, instance_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(
                command=["systemctl", "--user", "status", f"{instance_name}.service"],
                return_code=3,
                stdout="Active: inactive (dead)",
                stderr="",
            )

        def logs(self, instance_name: str, lines: int = 100, execute: bool = False) -> CommandResult:
            return CommandResult(
                command=["journalctl", "--user-unit", f"{instance_name}.service", "-n", str(lines)],
                return_code=0,
                stdout="EnvironmentFile=/missing.env\nNo such file or directory",
                stderr="",
            )

    monkeypatch.setattr(cli, "SystemdService", DiagnosticSystemdService)

    result = runner.invoke(app, ["status", "openclaw-developer", "--execute"])

    assert result.exit_code == 0
    assert "inactive (dead)" in result.output
    assert "Recent journal entries for failure analysis:" in result.output
    assert "No such file or directory" in result.output


def test_status_cluster_json(monkeypatch: object) -> None:
    from clawake import cli

    monkeypatch.setattr(cli, "SystemdService", FakeSystemdService)
    result = runner.invoke(
        app,
        [
            "status-cluster",
            "--config",
            str(Path("examples/staff/team.yml")),
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


def test_status_cluster_execute_prints_cause(monkeypatch: object) -> None:
    from clawake import cli

    class ClusterDiagnosticSystemdService:
        def status(self, instance_name: str, execute: bool = False) -> CommandResult:
            if instance_name == "excalibot-developer":
                return CommandResult(
                    command=["systemctl", "--user", "status", f"{instance_name}.service"],
                    return_code=3,
                    stdout="Active: failed (Result: exit-code)",
                    stderr="",
                )
            return CommandResult(
                command=["systemctl", "--user", "status", f"{instance_name}.service"],
                return_code=0,
                stdout="Active: active (running)",
                stderr="",
            )

        def logs(self, instance_name: str, lines: int = 100, execute: bool = False) -> CommandResult:
            return CommandResult(
                command=["journalctl", "--user-unit", f"{instance_name}.service", "-n", str(lines)],
                return_code=0,
                stdout="Error: missing API key",
                stderr="",
            )

        def unit_name(self, instance_name: str) -> str:
            return f"{instance_name}.service"

    monkeypatch.setattr(cli, "SystemdService", ClusterDiagnosticSystemdService)

    result = runner.invoke(
        app,
        [
            "status-cluster",
            "--config",
            str(Path("examples/staff/team.yml")),
            "--format",
            "text",
            "--execute",
        ],
    )

    assert result.exit_code != 0
    assert "excalibot-product-owner [product_owner] state=healthy rc=0" in result.output
    assert "excalibot-developer [developer] state=failed rc=3" in result.output
    assert "cause: Error: missing API key" in result.output


def test_auto_onboard_dry_run() -> None:
        result = runner.invoke(
                app,
                [
                        "auto-onboard",
                        "--config",
                        str(Path("examples/staff/team.yml")),
                        "--instance",
                        "excalibot-product-owner",
                ],
        )

        assert result.exit_code == 0
        assert "Auto-onboard plan for excalibot-product-owner" in result.output
        assert "DRY RUN auto-onboard complete" in result.output
        assert "Use openclaw commands directly inside this instance" in result.output
        assert "models auth login --provider openai --device-code" in result.output


def test_auto_onboard_execute_writes_openclaw_json(tmp_path: Path) -> None:
        env_file = tmp_path / "product-owner.env"
        env_file.write_text(
                "\n".join(
                        [
                                "OPENCLAW_GATEWAY_BIND=local",
                                "OPENCLAW_MODEL_PROVIDER=openai",
                                "OPENCLAW_MODEL=gpt-5.3-codex",
                                "OPENCLAW_MESSAGING_CHANNEL=discord",
                                "DISCORD_BOT_TOKEN=test-token",
                        ]
                )
                + "\n",
                encoding="utf-8",
        )

        state_root = tmp_path / "state"
        state_root.mkdir(parents=True, exist_ok=True)

        cfg = tmp_path / "product.yml"
        cfg_data = {
                "version": 1,
                "cluster": {"name": "c", "mode": "single_host", "primary_host": "a"},
                "hosts": [{"name": "a"}],
                "instances": [
                        {
                                "name": "one",
                                "host": "a",
                                "role": "developer",
                                "workspace_path": "/tmp/one/workspace",
                                "config_path": "/tmp/one/config",
                                "state_path": str(state_root),
                                "quadlet_path": "one.container",
                                "container_name": "one",
                                "image": {"repository": "ghcr.io/x", "tag": "1"},
                                "env_files": [str(env_file)],
                                "auto_onboard": {
                                        "required_env": [
                                                "OPENCLAW_MODEL_PROVIDER",
                                                "OPENCLAW_MODEL",
                                                "OPENCLAW_MESSAGING_CHANNEL",
                                        ],
                                        "openclaw_config": {
                                                "gateway": {"mode": "$ENV:OPENCLAW_GATEWAY_BIND"},
                                                "model": {
                                                        "provider": "$ENV:OPENCLAW_MODEL_PROVIDER",
                                                        "name": "$ENV:OPENCLAW_MODEL",
                                                },
                                                "messaging": {
                                                        "channel": "$ENV:OPENCLAW_MESSAGING_CHANNEL",
                                                        "discord": {"bot_token": "$ENV?:DISCORD_BOT_TOKEN"},
                                                },
                                        },
                                },
                                "dashboard": {"friendly_name": "One"},
                        }
                ],
        }
        cfg.write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

        result = runner.invoke(
                app,
                [
                        "auto-onboard",
                        "--config",
                        str(cfg),
                        "--instance",
                        "one",
                        "--execute",
                ],
        )

        assert result.exit_code == 0
        output_file = state_root / "openclaw.json"
        assert output_file.exists()
        payload = json.loads(output_file.read_text(encoding="utf-8"))
        assert payload["model"]["name"] == "gpt-5.3-codex"
        assert payload["messaging"]["channel"] == "discord"


def test_auto_onboard_fails_when_required_env_missing(tmp_path: Path) -> None:
        env_file = tmp_path / "product-owner.env"
        env_file.write_text("OPENCLAW_MODEL_PROVIDER=openai\n", encoding="utf-8")

        cfg = tmp_path / "product.yml"
        cfg_data = {
                "version": 1,
                "cluster": {"name": "c", "mode": "single_host", "primary_host": "a"},
                "hosts": [{"name": "a"}],
                "instances": [
                        {
                                "name": "one",
                                "host": "a",
                                "role": "developer",
                                "workspace_path": "/tmp/one/workspace",
                                "config_path": "/tmp/one/config",
                                "state_path": "/tmp/one/state",
                                "quadlet_path": "one.container",
                                "container_name": "one",
                                "image": {"repository": "ghcr.io/x", "tag": "1"},
                                "env_files": [str(env_file)],
                                "auto_onboard": {
                                        "required_env": ["OPENCLAW_MODEL_PROVIDER", "OPENCLAW_MODEL"],
                                        "openclaw_config": {
                                                "model": {
                                                        "provider": "$ENV:OPENCLAW_MODEL_PROVIDER",
                                                        "name": "$ENV:OPENCLAW_MODEL",
                                                }
                                        },
                                },
                                "dashboard": {"friendly_name": "One"},
                        }
                ],
        }
        cfg.write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

        result = runner.invoke(
                app,
                [
                        "auto-onboard",
                        "--config",
                        str(cfg),
                        "--instance",
                        "one",
                ],
        )

        assert result.exit_code != 0
        assert "Missing required environment variables" in result.output
        assert "OPENCLAW_MODEL" in result.output


def test_teardown_dry_run_cluster() -> None:
    result = runner.invoke(
        app,
        [
            "teardown",
            "--config",
            str(Path("examples/staff/team.yml")),
        ],
    )

    assert result.exit_code == 0
    assert "Teardown plan for cluster" in result.output
    assert "$ systemctl --user stop excalibot-product-owner.service" in result.output
    assert "$ podman rm -f excalibot-product-owner" in result.output
    assert "DRY RUN teardown complete" in result.output


def test_remove_alias_calls_teardown() -> None:
    result = runner.invoke(
        app,
        [
            "remove",
            "--config",
            str(Path("examples/staff/team.yml")),
            "--instance",
            "excalibot-product-owner",
        ],
    )

    assert result.exit_code == 0
    assert "Teardown plan for cluster" in result.output
    assert "excalibot-product-owner" in result.output


def test_teardown_skips_shared_image_without_force(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    cfg = tmp_path / "shared-image.yml"
    cfg.write_text(
        """
version: 1
cluster:
  name: c
  mode: single_host
  primary_host: a
hosts:
  - name: a
    quadlet_root: /tmp/quadlet
instances:
  - name: one
    host: a
    role: developer
    workspace_path: /tmp/one/workspace
    config_path: /tmp/one/config
    state_path: /tmp/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
  - name: two
    host: a
    role: product_owner
    workspace_path: /tmp/two/workspace
    config_path: /tmp/two/config
    state_path: /tmp/two/state
    quadlet_path: two.container
    container_name: two
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: Two}
""",
        encoding="utf-8",
    )

    class RecordImageRemovalSystemdService:
        image_removals = 0

        def stop(self, instance_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(["systemctl", "--user", "stop", f"{instance_name}.service"], 0, "ok", "")

        def disable(self, instance_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(["systemctl", "--user", "disable", f"{instance_name}.service"], 0, "ok", "")

        def remove_quadlet(self, quadlet_path: str, execute: bool = False) -> CommandResult:
            return CommandResult(["rm", "-f", quadlet_path], 0, "ok", "")

        def remove_container(self, container_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(["podman", "rm", "-f", container_name], 0, "ok", "")

        def daemon_reload(self, execute: bool = False) -> CommandResult:
            return CommandResult(["systemctl", "--user", "daemon-reload"], 0, "ok", "")

        def remove_image(self, image_ref: str, execute: bool = False) -> CommandResult:
            RecordImageRemovalSystemdService.image_removals += 1
            return CommandResult(["podman", "image", "rm", image_ref], 0, "ok", "")

    monkeypatch.setattr(cli, "SystemdService", RecordImageRemovalSystemdService)

    result = runner.invoke(
        app,
        [
            "teardown",
            "--config",
            str(cfg),
            "--instance",
            "one",
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert "Skipping image removal" in result.output
    assert RecordImageRemovalSystemdService.image_removals == 0


def test_teardown_force_image_removes_shared_image(monkeypatch: object, tmp_path: Path) -> None:
    from clawake import cli

    cfg = tmp_path / "shared-image-force.yml"
    cfg.write_text(
        """
version: 1
cluster:
  name: c
  mode: single_host
  primary_host: a
hosts:
  - name: a
    quadlet_root: /tmp/quadlet
instances:
  - name: one
    host: a
    role: developer
    workspace_path: /tmp/one/workspace
    config_path: /tmp/one/config
    state_path: /tmp/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
  - name: two
    host: a
    role: product_owner
    workspace_path: /tmp/two/workspace
    config_path: /tmp/two/config
    state_path: /tmp/two/state
    quadlet_path: two.container
    container_name: two
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: Two}
""",
        encoding="utf-8",
    )

    class RecordImageRemovalSystemdService:
        image_removals = 0

        def stop(self, instance_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(["systemctl", "--user", "stop", f"{instance_name}.service"], 0, "ok", "")

        def disable(self, instance_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(["systemctl", "--user", "disable", f"{instance_name}.service"], 0, "ok", "")

        def remove_quadlet(self, quadlet_path: str, execute: bool = False) -> CommandResult:
            return CommandResult(["rm", "-f", quadlet_path], 0, "ok", "")

        def remove_container(self, container_name: str, execute: bool = False) -> CommandResult:
            return CommandResult(["podman", "rm", "-f", container_name], 0, "ok", "")

        def daemon_reload(self, execute: bool = False) -> CommandResult:
            return CommandResult(["systemctl", "--user", "daemon-reload"], 0, "ok", "")

        def remove_image(self, image_ref: str, execute: bool = False) -> CommandResult:
            RecordImageRemovalSystemdService.image_removals += 1
            return CommandResult(["podman", "image", "rm", image_ref], 0, "ok", "")

    monkeypatch.setattr(cli, "SystemdService", RecordImageRemovalSystemdService)

    result = runner.invoke(
        app,
        [
            "teardown",
            "--config",
            str(cfg),
            "--instance",
            "one",
            "--force-image",
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert RecordImageRemovalSystemdService.image_removals == 1


def test_setup_quadlets_dry_run() -> None:
    result = runner.invoke(
        app,
        [
            "setup-quadlets",
            "--config",
            str(Path("examples/staff/team.yml")),
        ],
    )

    assert result.exit_code == 0
    assert "Setup plan for cluster" in result.output
    assert "DRY RUN setup-quadlets complete" in result.output


def test_restart_quadlets_member_execute(monkeypatch: object) -> None:
    from clawake import cli

    class RecordRestartSystemdService:
        restarted: list[str] = []

        def restart(self, instance_name: str, execute: bool = False) -> CommandResult:
            RecordRestartSystemdService.restarted.append(instance_name)
            return CommandResult(
                command=["systemctl", "--user", "restart", f"{instance_name}.service"],
                return_code=0,
                stdout="ok",
                stderr="",
            )

    monkeypatch.setattr(cli, "SystemdService", RecordRestartSystemdService)

    result = runner.invoke(
        app,
        [
            "restart-quadlets",
            "--config",
            str(Path("examples/staff/team.yml")),
            "--member",
            "excalibot-product-owner",
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert RecordRestartSystemdService.restarted == ["excalibot-product-owner"]


def test_status_quadlets_json(monkeypatch: object) -> None:
    from clawake import cli

    monkeypatch.setattr(cli, "SystemdService", FakeSystemdService)
    result = runner.invoke(
        app,
        [
            "status-quadlets",
            "--config",
            str(Path("examples/staff/team.yml")),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["cluster"] == "single-host-mvp"
    assert len(payload["instances"]) == 2


def test_teardown_quadlets_member_alias() -> None:
    result = runner.invoke(
        app,
        [
            "teardown-quadlets",
            "--config",
            str(Path("examples/staff/team.yml")),
            "--member",
            "excalibot-product-owner",
        ],
    )

    assert result.exit_code == 0
    assert "Teardown plan for cluster" in result.output
    assert "excalibot-product-owner" in result.output


def test_setup_quadlets_execute_writes_openclaw_config(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    from clawake import cli

    class RecordingSystemdService:
        daemon_reload_calls = 0
        restart_calls = 0

        def daemon_reload(self, execute: bool = False) -> CommandResult:
            RecordingSystemdService.daemon_reload_calls += 1
            return CommandResult(
                command=["systemctl", "--user", "daemon-reload"],
                return_code=0,
                stdout="ok",
                stderr="",
            )

        def restart(self, instance_name: str, execute: bool = False) -> CommandResult:
            RecordingSystemdService.restart_calls += 1
            return CommandResult(
                command=["systemctl", "--user", "restart", f"{instance_name}.service"],
                return_code=0,
                stdout="ok",
                stderr="",
            )

    monkeypatch.setattr(cli, "SystemdService", RecordingSystemdService)

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    quadlet_root = tmp_path / "quadlets"
    env_file = tmp_path / "instance.env"
    env_file.write_text(
        "OPENCLAW_GATEWAY_BIND=local\nOPENCLAW_GATEWAY_TOKEN=test-token\n",
        encoding="utf-8",
    )

    config_file = tmp_path / "inventory.yml"
    config_data = {
        "version": 1,
        "cluster": {
            "name": "c",
            "mode": "single_host",
            "primary_host": "h",
        },
        "hosts": [{"name": "h", "quadlet_root": str(quadlet_root)}],
        "instances": [
            {
                "name": "one",
                "host": "h",
                "role": "developer",
                "workspace_path": str(workspace),
                "state_path": str(tmp_path / "runtime" / "state"),
                "quadlet_path": "one.container",
                "container_name": "one",
                "image": {"repository": "ghcr.io/openclaw/openclaw", "tag": "2026.6.5"},
                "env_files": [str(env_file)],
                "auto_onboard": {
                    "required_env": ["OPENCLAW_GATEWAY_BIND", "OPENCLAW_GATEWAY_TOKEN"],
                    "openclaw_config": {
                        "gateway": {
                            "mode": "$ENV:OPENCLAW_GATEWAY_BIND",
                            "auth": {"token": "$ENV:OPENCLAW_GATEWAY_TOKEN"},
                        }
                    },
                },
                "dashboard": {"friendly_name": "One"},
            }
        ],
    }
    config_file.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    output = tmp_path / "rendered"
    result = runner.invoke(
        app,
        [
            "setup-quadlets",
            "--config",
            str(config_file),
            "--output",
            str(output),
            "--execute",
        ],
    )

    assert result.exit_code == 0
    state_file = tmp_path / "runtime" / "state" / "openclaw.json"
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["gateway"]["mode"] == "local"
    assert payload["gateway"]["auth"]["token"] == "test-token"
    assert RecordingSystemdService.daemon_reload_calls == 1
    assert RecordingSystemdService.restart_calls == 1
