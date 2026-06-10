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

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/product.yml"))])
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
    profile: internal
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
    profile: internal
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

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/product.yml"))])

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

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/product.yml"))])

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

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/product.yml"))])

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

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/product.yml"))])

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

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/product.yml"))])

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
            str(Path("examples/staff/product.yml")),
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
            str(Path("examples/staff/product.yml")),
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


def test_status_cluster_execute_prints_cause(monkeypatch: object) -> None:
    from clawake import cli

    class ClusterDiagnosticSystemdService:
        def status(self, instance_name: str, execute: bool = False) -> CommandResult:
            if instance_name == "openclaw-developer":
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
            str(Path("examples/staff/product.yml")),
            "--format",
            "text",
            "--execute",
        ],
    )

    assert result.exit_code != 0
    assert "openclaw-product-owner [product_owner/public] state=healthy rc=0" in result.output
    assert "openclaw-developer [developer/internal] state=failed rc=3" in result.output
    assert "cause: Error: missing API key" in result.output


def test_auto_onboard_dry_run() -> None:
        result = runner.invoke(
                app,
                [
                        "auto-onboard",
                        "--config",
                        str(Path("examples/staff/product.yml")),
                        "--instance",
                        "excalibot-product-owner",
                ],
        )

        assert result.exit_code == 0
        assert "Auto-onboard plan for excalibot-product-owner" in result.output
        assert "DRY RUN auto-onboard complete" in result.output
        assert "Use openclaw --profile public" in result.output
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

        config_root = tmp_path / "cfg"
        config_root.mkdir(parents=True, exist_ok=True)

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
                                "profile": "internal",
                                "workspace_path": "/tmp/one/workspace",
                                "config_path": str(config_root),
                                "state_path": "/tmp/one/state",
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
        output_file = config_root / "openclaw.json"
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
                                "profile": "internal",
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
