from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Literal

import typer

from clawake.config import ImageSpec, InstanceSpec, Inventory, load_inventory
from clawake.services.backup import backup_instance, prune_backups
from clawake.services.gateway_config import ensure_control_ui_config
from clawake.services.image_check import ImageCheckError, check_image_availability
from clawake.services.render import render_instance_assets
from clawake.services.runtime_upgrade import (
    doctor_command,
    ensure_browser_cache,
    is_browser_image,
    run_doctor,
    verify_runtime,
    wait_for_health,
)
from clawake.services.systemd import CommandResult, SystemdService
from clawake.services.upgrade import apply_upgrade, backup_config, build_upgrade_plan

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

app = typer.Typer(help="OpenClaw operations manager for rootless Podman + Quadlet")

ConfigPath = Annotated[Path, typer.Option(..., "--config", "-c", exists=True, dir_okay=False)]
OptionalMemberName = Annotated[str | None, typer.Option("--member", "-m")]
ExecuteFlag = Annotated[bool, typer.Option("--execute")]
StatusFormat = Annotated[Literal["text", "json"], typer.Option("--format")]
ShowTokenUrlFlag = Annotated[bool, typer.Option("--show-token-url")]
TargetTag = Annotated[str, typer.Option(..., "--to", help="Target OpenClaw image tag")]
TargetDigest = Annotated[str | None, typer.Option("--digest", help="Immutable target digest")]

_ENV_LINE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


def _load(path: Path) -> Inventory:
    return load_inventory(path)


def _template_root() -> Path:
    return Path(__file__).resolve().parents[2] / "templates"


def _instance_by_name(inventory: Inventory, name: str) -> InstanceSpec:
    for instance in inventory.instances:
        if instance.name == name:
            return instance
    raise typer.BadParameter(f"Unknown member '{name}'")


def _select_instances(inventory: Inventory, member: str | None) -> list[InstanceSpec]:
    if member is None:
        return list(inventory.instances)
    return [_instance_by_name(inventory, member)]


def _print_result(result: CommandResult) -> None:
    typer.echo(f"$ {' '.join(result.command)}")
    if result.stdout:
        typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr)


def _status_state(result: CommandResult) -> str:
    if result.return_code == 0:
        return "healthy"
    return "failed"


def _status_needs_diagnostics(result: CommandResult) -> bool:
    details = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    if result.return_code != 0:
        return True
    return any(
        token in details for token in ("inactive (dead)", "failed", "activating (auto-restart)")
    )


def _status_diagnostics(service: SystemdService, instance_name: str) -> CommandResult | None:
    logs_result = service.logs(instance_name, lines=50, execute=True)
    if not logs_result.stdout and not logs_result.stderr:
        return None
    return logs_result


def _diagnostic_summary(result: CommandResult | None) -> str | None:
    if result is None:
        return None
    for line in (result.stdout or result.stderr).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _is_tolerated_teardown_error(result: CommandResult) -> bool:
    details = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    tolerated_markers = ("not loaded", "not found", "no such container", "does not exist")
    return any(marker in details for marker in tolerated_markers)


def _load_env_file_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not _ENV_LINE_PATTERN.fullmatch(line):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _instance_env_values(instance: InstanceSpec) -> dict[str, str]:
    merged: dict[str, str] = {}
    for raw_path in instance.env_files:
        merged.update(_load_env_file_values(Path(raw_path).expanduser()))
    return merged


def _dashboard_host_url(instance: InstanceSpec) -> str:
    gateway_port = instance.gateway_runtime.gateway_container_port
    published_gateway_port = next(
        (
            port
            for port in instance.ports
            if port.container_port == gateway_port and port.protocol == "tcp"
        ),
        None,
    )
    host_port = published_gateway_port.host_port if published_gateway_port else gateway_port
    return f"http://127.0.0.1:{host_port}/"


def _deploy_instance_assets(
    instance: InstanceSpec,
    inventory: Inventory,
    output: Path = Path(".rendered"),
) -> list[Path]:
    host_map = {host.name: host for host in inventory.hosts}
    destination_root = Path(host_map[instance.host].quadlet_root).expanduser()
    deployed: list[Path] = []
    for relative_path, rendered_text in render_instance_assets(
        instance, template_root=_template_root()
    ).items():
        rendered_file = output / relative_path
        rendered_file.parent.mkdir(parents=True, exist_ok=True)
        rendered_file.write_text(rendered_text, encoding="utf-8")
        destination = destination_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered_file, destination)
        deployed.append(destination)
    return deployed


@app.command("upgrade")
def upgrade_member(
    config: ConfigPath,
    member: Annotated[str, typer.Option(..., "--member", "-m")],
    target_tag: TargetTag,
    digest: TargetDigest = None,
    execute: ExecuteFlag = False,
) -> None:
    """Safely upgrade one member, including backup, migration, and health checks."""
    inventory = _load(config)
    instance = _instance_by_name(inventory, member)
    target_digest = digest
    if target_digest is None and target_tag == instance.image.tag:
        target_digest = instance.image.digest
    if not target_digest:
        raise typer.BadParameter(
            "An immutable --digest is required when changing tags; "
            "Clawake will not follow an unpinned image tag."
        )

    plan = build_upgrade_plan(config, member, target_tag, target_digest)
    target = ImageSpec(
        repository=instance.image.repository,
        tag=plan.next_tag,
        digest=plan.next_digest,
    )
    typer.echo(f"Upgrade plan for member '{member}':")
    typer.echo(f"  image: {plan.previous_tag} -> {plan.next_tag}")
    typer.echo(f"  digest: {plan.previous_digest or 'unpinned'} -> {plan.next_digest}")
    typer.echo(f"  backup: {'yes' if instance.backup_policy.pre_mutation else 'no'}")
    typer.echo(f"  migration: {' '.join(doctor_command(instance, target)[-5:])}")
    typer.echo(f"  health: {_dashboard_host_url(instance).rstrip('/')}{instance.health.path}")
    if not execute:
        typer.echo("DRY RUN upgrade complete. Re-run with --execute to mutate state.")
        return

    service = SystemdService()
    backup_dir = Path(".backups")
    stopped = False
    config_changed = False
    runtime_backup: Path | None = None
    config_backup: Path | None = None

    try:
        typer.echo("Verifying pinned image in registry...")
        check_image_availability(target)

        stop_result = service.stop(instance.name, execute=True)
        _print_result(stop_result)
        if stop_result.return_code != 0:
            raise RuntimeError(stop_result.stderr or "failed to stop service")
        stopped = True

        if instance.backup_policy.enabled and instance.backup_policy.pre_mutation:
            config_backup = backup_config(config, backup_dir)
            runtime_backup = backup_instance(instance, backup_dir, execute=True)
            typer.echo(f"Created config backup: {config_backup}")
            typer.echo(f"Created runtime backup: {runtime_backup}")

        if is_browser_image(target):
            cache_path = ensure_browser_cache(instance)
            typer.echo(f"Prepared private browser cache: {cache_path}")

        typer.echo("Running OpenClaw safe migrations in a one-shot container...")
        doctor_result = run_doctor(instance, target)
        if doctor_result.returncode != 0:
            details = doctor_result.stderr.strip() or doctor_result.stdout.strip()
            raise RuntimeError(f"OpenClaw migration failed: {details}")

        apply_upgrade(config, instance.name, target.tag, target.digest)
        config_changed = True
        updated_inventory = _load(config)
        updated_instance = _instance_by_name(updated_inventory, member)
        ensure_control_ui_config(updated_instance)
        for deployed in _deploy_instance_assets(updated_instance, updated_inventory):
            typer.echo(f"Deployed {deployed}")

        reload_result = service.daemon_reload(execute=True)
        _print_result(reload_result)
        if reload_result.return_code != 0:
            raise RuntimeError(reload_result.stderr or "systemd daemon-reload failed")

        restart_result = service.restart(instance.name, execute=True)
        _print_result(restart_result)
        if restart_result.return_code != 0:
            raise RuntimeError(restart_result.stderr or "service restart failed")

        healthy, health_details = wait_for_health(updated_instance)
        if not healthy:
            raise RuntimeError(f"health check failed: {health_details}")

        runtime = verify_runtime(updated_instance, target)
        if not runtime.healthy:
            raise RuntimeError(f"runtime verification failed: {runtime.error}")

        typer.echo(f"Upgrade complete: {runtime.version}")
        typer.echo(f"Running image: {runtime.image_name}")
        typer.echo(f"Health check: {health_details}")
        if runtime_backup:
            prune_backups(backup_dir, f"{instance.name}-", instance.backup_policy.retention)
        if config_backup:
            prune_backups(backup_dir, f"{config.stem}-", instance.backup_policy.retention)
    except (ImageCheckError, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Upgrade failed: {exc}", err=True)
        if stopped and not config_changed:
            typer.echo("The config was not changed; attempting to restart the previous image.")
            recovery = service.restart(instance.name, execute=True)
            _print_result(recovery)
        elif config_changed:
            typer.echo("Stopping the failed upgraded service to prevent a restart loop.", err=True)
            stopped_result = service.stop(instance.name, execute=True)
            _print_result(stopped_result)
        if runtime_backup:
            typer.echo(f"Runtime recovery archive: {runtime_backup}", err=True)
        if config_backup:
            typer.echo(f"Config recovery file: {config_backup}", err=True)
        typer.echo(
            f"Inspect logs with: journalctl --user-unit {service.unit_name(instance.name)} -n 100",
            err=True,
        )
        raise typer.Exit(code=1) from exc


@app.command("onboard-member")
def onboard_member(
    config: ConfigPath,
    member: Annotated[str, typer.Option(..., "--member", "-m")],
    execute: ExecuteFlag = False,
) -> None:
    """Run OpenClaw's interactive onboarding inside one managed container."""
    inventory = _load(config)
    instance = _instance_by_name(inventory, member)
    command = [
        "podman",
        "exec",
        "--interactive",
        "--tty",
        instance.container_name,
        "openclaw",
        "onboard",
        "--workspace",
        "/workspace",
        "--skip-bootstrap",
        "--no-install-daemon",
    ]

    typer.echo(f"Onboarding plan for member '{instance.name}':")
    typer.echo(f"$ {' '.join(command)}")
    if not execute:
        typer.echo("DRY RUN onboard-member complete. Re-run with --execute to open the TUI.")
        return

    onboard_result = subprocess.run(command, check=False)
    if onboard_result.returncode != 0:
        raise typer.Exit(code=onboard_result.returncode or 1)

    restart_result = SystemdService().restart(instance.name, execute=True)
    _print_result(restart_result)
    if restart_result.return_code != 0:
        raise typer.Exit(code=1)


@app.command("diagnose-dashboard")
def diagnose_dashboard(
    config: ConfigPath,
    member: OptionalMemberName = None,
    format: StatusFormat = "text",
    show_token_url: ShowTokenUrlFlag = False,
) -> None:
    """Show dashboard URLs and token diagnostics for selected members."""
    inventory = _load(config)
    selected = _select_instances(inventory, member)
    if not selected:
        typer.echo("No matching members selected for dashboard diagnosis")
        return

    rows: list[dict[str, object]] = []
    for instance in selected:
        dashboard_url = _dashboard_host_url(instance)
        env_values = _instance_env_values(instance)
        token = env_values.get("OPENCLAW_GATEWAY_TOKEN", "")
        auth_url = f"{dashboard_url}#token={token}" if token else None
        row = {
            "instance": instance.name,
            "role": instance.role,
            "dashboard_url": dashboard_url,
            "token_present": bool(token),
            "token_env_key": "OPENCLAW_GATEWAY_TOKEN",
            "token_env_files": [str(Path(path).expanduser()) for path in instance.env_files],
            "auth_url": auth_url if show_token_url else None,
        }
        rows.append(row)

    if format == "json":
        typer.echo(
            json.dumps(
                {
                    "cluster": inventory.cluster.name,
                    "mode": inventory.cluster.mode,
                    "instances": rows,
                },
                indent=2,
            )
        )
        return

    typer.echo(f"Dashboard diagnosis for cluster '{inventory.cluster.name}'")
    for row in rows:
        typer.echo(f"- {row['instance']} [{row['role']}]")
        typer.echo(f"  dashboard: {row['dashboard_url']}")
        typer.echo(f"  token_env_key: {row['token_env_key']}")
        typer.echo(f"  token_present: {'yes' if row['token_present'] else 'no'}")
        for env_file in row["token_env_files"]:
            typer.echo(f"  env_file: {env_file}")
        if show_token_url and row["auth_url"]:
            typer.echo(f"  auth_url: {row['auth_url']}")
        elif row["token_present"]:
            typer.echo("  hint: re-run with --show-token-url to print URL fragment auth")


@app.command("setup-quadlets")
def setup_quadlets(
    config: ConfigPath,
    member: OptionalMemberName = None,
    execute: ExecuteFlag = False,
) -> None:
    """Render and apply desired Quadlet definitions for the current team."""
    inventory = _load(config)
    selected = _select_instances(inventory, member)
    if not selected:
        typer.echo("No matching members selected for setup")
        return

    output = Path(".rendered")
    output.mkdir(parents=True, exist_ok=True)
    template_root = _template_root()
    host_map = {host.name: host for host in inventory.hosts}
    changed_artifacts: list[tuple[InstanceSpec, Path, Path]] = []
    changed_instance_names: set[str] = set()

    for instance in selected:
        host = host_map[instance.host]
        for relative_path, rendered_text in render_instance_assets(
            instance,
            template_root=template_root,
        ).items():
            rendered_file = output / relative_path
            rendered_file.parent.mkdir(parents=True, exist_ok=True)
            rendered_file.write_text(rendered_text, encoding="utf-8")

            destination = Path(host.quadlet_root).expanduser() / relative_path
            current_text = destination.read_text(encoding="utf-8") if destination.exists() else ""
            if current_text != rendered_text:
                changed_artifacts.append((instance, rendered_file, destination))
                changed_instance_names.add(instance.name)

    typer.echo(
        f"Setup plan for cluster '{inventory.cluster.name}' ({inventory.cluster.mode}): "
        f"{len(changed_instance_names)}/{len(selected)} member(s) changed"
    )

    for instance, rendered_file, destination in changed_artifacts:
        typer.echo(f" - {instance.name} [{instance.role}] {rendered_file} -> {destination}")

    if not execute:
        typer.echo("DRY RUN setup-quadlets complete. Re-run with --execute to mutate state.")
        return

    service = SystemdService()
    failed = False

    # Podman requires bind-mount sources to exist before starting the unit.
    for instance in selected:
        runtime_state = Path(instance.workspace_path).expanduser() / ".openclaw"
        runtime_state.mkdir(parents=True, exist_ok=True)
        if is_browser_image(instance.image):
            ensure_browser_cache(instance)
        gateway_config, gateway_config_changed = ensure_control_ui_config(instance)
        if gateway_config_changed:
            typer.echo(f"Updated local Control UI access in {gateway_config}")

    for _instance, rendered_file, destination in changed_artifacts:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered_file, destination)
        typer.echo(f"Deployed {rendered_file} -> {destination}")

    reload_result = service.daemon_reload(execute=True)
    _print_result(reload_result)
    failed = failed or reload_result.return_code != 0

    if not changed_artifacts:
        typer.echo("No rendered changes detected; ensuring selected services are running.")

    # Setup is an idempotent reconciliation operation: even when the rendered
    # Quadlets already match, the selected service may be stopped or may never
    # have been started. Restart every selected member after daemon-reload.
    for instance in selected:
        restart_result = service.restart(instance.name, execute=True)
        _print_result(restart_result)
        failed = failed or restart_result.return_code != 0

    if failed:
        raise typer.Exit(code=1)


@app.command("restart-quadlets")
def restart_quadlets(
    config: ConfigPath,
    member: OptionalMemberName = None,
    execute: ExecuteFlag = False,
) -> None:
    """Restart selected or all managed services after config/image changes."""
    inventory = _load(config)
    selected = _select_instances(inventory, member)
    if not selected:
        typer.echo("No matching members selected for restart")
        return

    service = SystemdService()
    failed = False
    for instance in selected:
        result = service.restart(instance.name, execute=execute)
        _print_result(result)
        if result.return_code != 0:
            failed = True

    if not execute:
        typer.echo("DRY RUN restart-quadlets complete. Re-run with --execute to mutate state.")
        return

    if failed:
        raise typer.Exit(code=1)


@app.command("status-quadlets")
def status_quadlets(
    config: ConfigPath,
    member: OptionalMemberName = None,
    format: StatusFormat = "text",
) -> None:
    """Aggregate per-member runtime status with optional machine-readable output."""
    inventory = _load(config)
    selected = _select_instances(inventory, member)
    service = SystemdService()
    rows: list[dict[str, object]] = []

    for instance in selected:
        result = service.status(instance.name, execute=True)
        diagnostics = None
        if _status_needs_diagnostics(result):
            diagnostics = _status_diagnostics(service, instance.name)
        row = {
            "instance": instance.name,
            "role": instance.role,
            "state": _status_state(result),
            "return_code": result.return_code,
            "unit": service.unit_name(instance.name),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "diagnostics": (
                diagnostics.stdout
                if diagnostics and diagnostics.stdout
                else diagnostics.stderr
                if diagnostics
                else ""
            ),
        }
        rows.append(row)

    if format == "json":
        typer.echo(
            json.dumps(
                {
                    "cluster": inventory.cluster.name,
                    "mode": inventory.cluster.mode,
                    "instances": rows,
                },
                indent=2,
            )
        )
    else:
        typer.echo(f"Cluster: {inventory.cluster.name} ({inventory.cluster.mode})")
        for row in rows:
            typer.echo(
                f"- {row['instance']} [{row['role']}] state={row['state']} rc={row['return_code']}"
            )
            diagnostics_summary = _diagnostic_summary(
                CommandResult(command=[], return_code=0, stdout=str(row["diagnostics"]), stderr="")
                if row["diagnostics"]
                else None
            )
            if diagnostics_summary:
                typer.echo(f"  cause: {diagnostics_summary}")

    if any(int(row["return_code"]) != 0 for row in rows):
        raise typer.Exit(code=1)


@app.command("teardown-quadlets")
def teardown_quadlets(
    config: ConfigPath,
    member: OptionalMemberName = None,
    execute: ExecuteFlag = False,
) -> None:
    """Remove managed runtime services for selected members or whole teams."""
    inventory = _load(config)
    selected = _select_instances(inventory, member)
    if not selected:
        typer.echo("No matching members selected for teardown")
        return

    host_map = {host.name: host for host in inventory.hosts}
    service = SystemdService()
    failed = False

    typer.echo(
        f"Teardown plan for cluster '{inventory.cluster.name}': {len(selected)} member(s) "
        f"(execute={execute})"
    )

    for chosen in selected:
        host = host_map[chosen.host]
        quadlet_targets = [
            Path(host.quadlet_root).expanduser() / artifact_path
            for artifact_path in chosen.quadlet_artifact_paths
        ]

        typer.echo(f"- Teardown {chosen.name} [{chosen.role}]")
        results = [
            service.stop(chosen.name, execute=execute),
            service.disable(chosen.name, execute=execute),
            service.remove_container(chosen.container_name, execute=execute),
        ]
        for quadlet_target in quadlet_targets:
            results.append(service.remove_quadlet(str(quadlet_target), execute=execute))
        for result in results:
            _print_result(result)
            if result.return_code != 0 and not _is_tolerated_teardown_error(result):
                failed = True

    reload_result = service.daemon_reload(execute=execute)
    _print_result(reload_result)
    if reload_result.return_code != 0:
        failed = True

    if not execute:
        typer.echo("DRY RUN teardown-quadlets complete. Re-run with --execute to mutate state.")
        return

    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
