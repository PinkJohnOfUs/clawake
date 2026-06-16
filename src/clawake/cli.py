from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Annotated, Literal

import typer

from clawake.config import InstanceSpec, Inventory, load_inventory
from clawake.services.onboarding import (
    AutoOnboardError,
    AutoOnboardPlan,
    auto_onboard_would_change,
    build_auto_onboard_plan,
    write_auto_onboard_config,
)
from clawake.services.render import image_ref, render_instance_assets
from clawake.services.systemd import CommandResult, SystemdService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

app = typer.Typer(help="OpenClaw operations manager for rootless Podman + Quadlet")

ConfigPath = Annotated[Path, typer.Option(..., "--config", "-c", exists=True, dir_okay=False)]
OptionalMemberName = Annotated[str | None, typer.Option("--member", "-m")]
ExecuteFlag = Annotated[bool, typer.Option("--execute")]
StatusFormat = Annotated[Literal["text", "json"], typer.Option("--format")]
ShowTokenUrlFlag = Annotated[bool, typer.Option("--show-token-url")]

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
    return any(token in details for token in ("inactive (dead)", "failed", "activating (auto-restart)"))


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


def _prepare_runtime_mounts(instance: InstanceSpec, execute: bool) -> list[str]:
    actions: list[str] = []

    workspace_path = Path(instance.workspace_path).expanduser()
    team_definition_path = Path(instance.team_definition_path).expanduser()
    runtime_dir = workspace_path / ".openclaw"
    state_file = runtime_dir / "openclaw.json"

    if not workspace_path.exists() or not workspace_path.is_dir():
        raise typer.BadParameter(
            f"Workspace path missing or not a directory for '{instance.name}': {workspace_path}"
        )

    if not team_definition_path.exists():
        raise typer.BadParameter(
            f"Team definition path missing for '{instance.name}': {team_definition_path}"
        )

    for directory in (runtime_dir,):
        if directory.exists() and not directory.is_dir():
            raise typer.BadParameter(
                f"Runtime path is not a directory for '{instance.name}': {directory}"
            )
        if not directory.exists():
            if execute:
                directory.mkdir(parents=True, exist_ok=True)
                actions.append(f"Prepared runtime directory for {instance.name}: {directory}")
            else:
                actions.append(f"DRY RUN prepare runtime directory for {instance.name}: {directory}")

    if state_file.exists() and not state_file.is_file():
        raise typer.BadParameter(
            f"Runtime state path is not a regular file for '{instance.name}': {state_file}"
        )

    if not state_file.exists():
        if execute:
            state_file.write_text("{}\n", encoding="utf-8")
            actions.append(f"Prepared runtime state file for {instance.name}: {state_file}")
        else:
            actions.append(f"DRY RUN prepare runtime state file for {instance.name}: {state_file}")

    return actions


def _config_contains_required_shape(actual: object, expected: object) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        for key, child in expected.items():
            if key not in actual:
                return False
            if not _config_contains_required_shape(actual[key], child):
                return False
        return True
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        if len(actual) < len(expected):
            return False
        for index, child in enumerate(expected):
            if not _config_contains_required_shape(actual[index], child):
                return False
        return True
    return actual == expected


def _auto_onboard_needs_repair(instance: InstanceSpec, plan: AutoOnboardPlan) -> bool:
    if not instance.auto_onboard or not instance.auto_onboard.enabled:
        return False
    return auto_onboard_would_change(plan)


def _repair_runtime_state_file(instance: InstanceSpec, execute: bool) -> list[str]:
    actions: list[str] = []
    state_dir = Path(instance.workspace_path).expanduser() / ".openclaw"
    state_file = state_dir / "openclaw.json"

    if state_file.exists() and not state_file.is_file():
        raise typer.BadParameter(
            f"Runtime state path is not a regular file for '{instance.name}': {state_file}"
        )

    for stale_candidate in sorted(state_dir.glob("openclaw.json.unreadable*")):
        if execute:
            stale_candidate.unlink(missing_ok=True)
            actions.append(
                f"Removed stale runtime state artifact for {instance.name}: {stale_candidate}"
            )
        else:
            actions.append(
                f"DRY RUN remove stale runtime state artifact for {instance.name}: {stale_candidate}"
            )

    if not state_file.exists():
        return actions

    current_uid = os.getuid()
    current_gid = os.getgid()
    stat_result = state_file.stat()
    needs_repair = False
    reasons: list[str] = []

    if stat_result.st_uid != current_uid or stat_result.st_gid != current_gid:
        needs_repair = True
        reasons.append(
            f"owner {stat_result.st_uid}:{stat_result.st_gid} != {current_uid}:{current_gid}"
        )

    payload = "{}\n"
    read_error: OSError | None = None
    try:
        payload = state_file.read_text(encoding="utf-8")
    except OSError as exc:
        needs_repair = True
        read_error = exc
        reasons.append(f"unreadable ({exc})")

    if not needs_repair:
        return actions

    reason_text = ", ".join(reasons)
    if not execute:
        actions.append(
            f"DRY RUN repair runtime state file for {instance.name}: {state_file} ({reason_text})"
        )
        return actions

    temp_state_file = state_file.with_name(f".{state_file.name}.clawake-repair")
    temp_state_file.write_text(payload, encoding="utf-8")
    temp_state_file.chmod(0o600)
    temp_state_file.replace(state_file)
    if read_error is not None:
        actions.append(
            f"Repaired runtime state file for {instance.name}: {state_file} "
            f"(fallback payload due to read error: {read_error})"
        )
    else:
        actions.append(
            f"Repaired runtime state file for {instance.name}: {state_file} ({reason_text})"
        )

    return actions


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

    auto_onboard_repairs: list[tuple[InstanceSpec, AutoOnboardPlan]] = []
    for instance in selected:
        if not instance.auto_onboard or not instance.auto_onboard.enabled:
            continue
        try:
            plan = build_auto_onboard_plan(instance)
        except AutoOnboardError as exc:
            raise typer.BadParameter(str(exc)) from exc

        if plan.missing_required_env:
            missing = ", ".join(plan.missing_required_env)
            raise typer.BadParameter(
                f"Missing required environment variables for auto-onboard member '{instance.name}': {missing}"
            )

        if _auto_onboard_needs_repair(instance, plan):
            auto_onboard_repairs.append((instance, plan))

    if not execute:
        for instance in selected:
            if instance.name not in changed_instance_names:
                continue
            for action in _prepare_runtime_mounts(instance, execute=False):
                typer.echo(action)
            for action in _repair_runtime_state_file(instance, execute=False):
                typer.echo(action)
        for instance, plan in auto_onboard_repairs:
            typer.echo(
                f"DRY RUN auto-onboard would write runtime config for {instance.name}: {plan.target_path}"
            )
        typer.echo("DRY RUN setup-quadlets complete. Re-run with --execute to mutate state.")
        return

    service = SystemdService()
    failed = False
    restart_targets: list[str] = []
    prepared_instances: set[str] = set()

    for instance, rendered_file, destination in changed_artifacts:
        if instance.name not in prepared_instances:
            for action in _prepare_runtime_mounts(instance, execute=True):
                typer.echo(action)
            for action in _repair_runtime_state_file(instance, execute=True):
                typer.echo(action)
            prepared_instances.add(instance.name)

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered_file, destination)
        typer.echo(f"Deployed {rendered_file} -> {destination}")
        if instance.name not in restart_targets:
            restart_targets.append(instance.name)

    if auto_onboard_repairs:
        for instance, plan in auto_onboard_repairs:
            write_auto_onboard_config(plan, execute=True)
            typer.echo(
                f"Auto-onboard repaired runtime config for {instance.name}: {plan.target_path}"
            )
            if instance.name not in restart_targets:
                restart_targets.append(instance.name)

    reload_result = service.daemon_reload(execute=True)
    _print_result(reload_result)
    failed = failed or reload_result.return_code != 0

    if not changed_artifacts and not auto_onboard_repairs:
        typer.echo("No rendered changes detected; daemon-reload completed.")

    for instance_name in restart_targets:
        restart_result = service.restart(instance_name, execute=True)
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
            "diagnostics": diagnostics.stdout if diagnostics and diagnostics.stdout else diagnostics.stderr if diagnostics else "",
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
                f"- {row['instance']} [{row['role']}] "
                f"state={row['state']} rc={row['return_code']}"
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
