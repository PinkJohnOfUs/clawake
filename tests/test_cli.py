import json
from pathlib import Path

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

    def unit_name(self, instance_name: str) -> str:
        return f"{instance_name}.service"

def test_validate_command(monkeypatch: object) -> None:
    from clawake import cli

    # Positive case: image check is a no-op (registry not required in unit tests)
    monkeypatch.setattr(cli, "check_image_availability", lambda _: None)

    result = runner.invoke(app, ["validate", "--config", str(Path("examples/staff/product.yml"))])
    assert result.exit_code == 0
    assert "is valid for cluster" in result.stdout


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
