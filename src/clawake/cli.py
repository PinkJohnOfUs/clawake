from __future__ import annotations

import difflib
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Annotated, Literal

import typer

from clawake.config import InstanceSpec, Inventory, load_inventory
from clawake.services.backup import backup_instance
from clawake.services.render import image_ref, render_instance, render_inventory
from clawake.services.systemd import CommandResult, SystemdService
from clawake.services.image_check import ImageCheckError, check_image_availability
from clawake.services.onboarding import (
    AutoOnboardError,
    AutoOnboardPlan,
    build_auto_onboard_plan,
    write_auto_onboard_config,
)
from clawake.services.upgrade import (
    apply_upgrade,
    backup_config,
    build_upgrade_plan,
    rollback_to_known_good,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

app = typer.Typer(help="OpenClaw operations manager for rootless Podman + Quadlet")

ConfigPath = Annotated[Path, typer.Option(..., "--config", "-c", exists=True, dir_okay=False)]
OutputPath = Annotated[Path, typer.Option("--output", "-o")]
TargetPath = Annotated[Path, typer.Option(..., "--target")]
ExecuteFlag = Annotated[bool, typer.Option("--execute")]
InstanceName = Annotated[str, typer.Option(..., "--instance", "-i")]
OptionalInstanceName = Annotated[str | None, typer.Option("--instance", "-i")]
TagValue = Annotated[str | None, typer.Option("--tag")]
DigestValue = Annotated[str | None, typer.Option("--digest")]
StatusFormat = Annotated[Literal["text", "json"], typer.Option("--format")]
ForceImageRemoval = Annotated[bool, typer.Option("--force-image")]
_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _load(path: Path) -> Inventory:
    return load_inventory(path)


def _template_root() -> Path:
    return Path(__file__).resolve().parents[2] / "templates"


def _instance_by_name(inventory: Inventory, name: str) -> InstanceSpec:
    for instance in inventory.instances:
        if instance.name == name:
            return instance
    raise typer.BadParameter(f"Unknown instance '{name}'")


def _print_result(result: CommandResult) -> None:
    typer.echo(f"$ {' '.join(result.command)}")
    if result.stdout:
        typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr)


def _status_state(result: CommandResult, execute: bool) -> str:
    if not execute:
        return "dry_run"
    if result.return_code == 0:
        return "healthy"
    return "failed"


def _status_needs_diagnostics(result: CommandResult) -> bool:
    details = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    if result.return_code != 0:
        return True
    return any(token in details for token in ("inactive (dead)", "failed", "activating (auto-restart)"))


def _status_diagnostics(service: SystemdService, instance_name: str, execute: bool) -> CommandResult | None:
    if not execute:
        return None
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
    tolerated_markers = (
        "not loaded",
        "not found",
        "no such container",
        "no such image",
        "image not known",
        "does not exist",
    )
    return any(marker in details for marker in tolerated_markers)

def _registry_host(image_ref: str) -> str:
    return image_ref.split("/", 1)[0]

def _enrich_public_image_hint(error: ImageCheckError) -> str:
    hint = error.hint or "Verify the image repository, tag, and digest, and confirm that the image is publicly reachable."
    reason = error.reason.lower()
    if _registry_host(error.image_ref) == "ghcr.io" and any(token in reason for token in ("unauthorized", "forbidden", "403", "access denied")):
        ghcr_hint = (
            "OpenClaw images are public and can be found here: "
            "https://github.com/openclaw/openclaw/pkgs/container/openclaw"
        )
        if ghcr_hint not in hint:
            hint = f"{hint} {ghcr_hint}"
    return hint

def _print_validation_failure(instance_name: str, error: ImageCheckError) -> None:
    typer.secho(
        f"[ERROR] {instance_name}: {error.image_ref} -> {error.reason}",
        fg="red",
        bold=True,
        err=True,
    )


def _print_validation_fix(hint: str) -> None:
    typer.secho(f"[fix] {hint}", fg="yellow", err=True)


def _validate_env_file(instance_name: str, env_file: str) -> list[str]:
    issues: list[str] = []
    path = Path(env_file).expanduser()

    if not path.exists():
        issues.append(f"[ERROR] {instance_name}: EnvironmentFile missing: {path}")
        return issues
    if not path.is_file():
        issues.append(f"[ERROR] {instance_name}: EnvironmentFile is not a regular file: {path}")
        return issues

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            issues.append(
                f"[ERROR] {instance_name}: invalid env entry in {path}:{line_number} (expected KEY=VALUE)"
            )
            continue
        key, _ = line.split("=", 1)
        if not _ENV_KEY_PATTERN.fullmatch(key.strip()):
            issues.append(
                f"[ERROR] {instance_name}: invalid env key in {path}:{line_number} ('{key.strip()}')"
            )
    return issues


def _prepare_runtime_mounts(instance: InstanceSpec, execute: bool) -> list[str]:
    actions: list[str] = []

    workspace_path = Path(instance.workspace_path).expanduser()
    config_dir = Path(instance.config_path).expanduser()
    state_dir = Path(instance.state_path).expanduser()
    state_file = state_dir / "openclaw.json"

    if not workspace_path.exists() or not workspace_path.is_dir():
        raise typer.BadParameter(
            f"Workspace path missing or not a directory for '{instance.name}': {workspace_path}"
        )

    for directory in (config_dir, state_dir):
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
    if expected is None:
        return True
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
    return True


def _auto_onboard_needs_repair(instance: InstanceSpec, plan: AutoOnboardPlan) -> bool:
    if not instance.auto_onboard or not instance.auto_onboard.enabled:
        return False

    target_path = plan.target_path
    if not target_path.exists() or not target_path.is_file():
        return True

    try:
        payload = json.loads(target_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True

    if not isinstance(payload, dict):
        return True
    return not _config_contains_required_shape(payload, plan.config)


def _repair_runtime_state_file(instance: InstanceSpec, execute: bool) -> list[str]:
    actions: list[str] = []
    state_dir = Path(instance.state_path).expanduser()
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


@app.command()
def validate(config: ConfigPath) -> None:
    """Validate inventory configuration and verify image availability."""
    inventory = _load(config)

    image_errors: list[tuple[str, ImageCheckError]] = []
    env_file_issues: list[str] = []

    for instance in inventory.instances:
        try:
            check_image_availability(instance.image)
        except ImageCheckError as exc:
            image_errors.append((instance.name, exc))

        for env_file in instance.env_files:
            env_file_issues.extend(_validate_env_file(instance.name, env_file))

    if image_errors or env_file_issues:
        typer.secho(
            "Validation failed: "
            f"{len(image_errors)} image check(s), {len(env_file_issues)} env file issue(s)",
            fg="red",
            bold=True,
            err=True,
        )
        hints: list[str] = []
        for instance_name, exc in image_errors:
            hint = _enrich_public_image_hint(exc)
            _print_validation_failure(instance_name, exc)
            if hint not in hints:
                hints.append(hint)

        for issue in env_file_issues:
            typer.secho(issue, fg="red", bold=True, err=True)

        if env_file_issues:
            hints.append("Create the missing env files and ensure each line uses KEY=VALUE syntax")

        for hint in hints:
            _print_validation_fix(hint)
        raise typer.Exit(1)

    typer.echo(f"OK: {config} is valid for cluster '{inventory.cluster.name}'")


@app.command()
def render(config: ConfigPath, output: OutputPath = Path(".rendered")) -> None:
    """Render Quadlet files from inventory."""
    inventory = _load(config)
    rendered = render_inventory(inventory, output_dir=output, template_root=_template_root())
    typer.echo(f"Rendered {len(rendered)} file(s) into {output}")


@app.command()
def plan(config: ConfigPath, output: OutputPath = Path(".rendered")) -> None:
    """Render and show file diffs against current output."""
    inventory = _load(config)
    output.mkdir(parents=True, exist_ok=True)
    template_root = _template_root()
    for instance in inventory.instances:
        target = output / instance.quadlet_path
        old = target.read_text(encoding="utf-8").splitlines() if target.exists() else []

        new_text = render_instance(instance, template_root=template_root)
        new = new_text.splitlines()
        diff = list(
            difflib.unified_diff(
                old,
                new,
                fromfile="current",
                tofile="rendered",
                lineterm="",
            )
        )
        if diff:
            typer.echo(f"--- Plan for {instance.name} ({target}) ---")
            typer.echo("\n".join(diff))
        else:
            typer.echo(f"No changes for {instance.name}")


@app.command()
def deploy(config: ConfigPath, target: TargetPath, execute: ExecuteFlag = False) -> None:
    """Deploy rendered Quadlet files to target path."""
    inventory = _load(config)
    rendered_dir = Path(".rendered")
    rendered = render_inventory(inventory, output_dir=rendered_dir, template_root=_template_root())

    for rendered_file in rendered:
        destination = target.expanduser() / rendered_file.relative_to(rendered_dir)
        if execute:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rendered_file, destination)
            typer.echo(f"Deployed {rendered_file} -> {destination}")
        else:
            typer.echo(f"DRY RUN deploy {rendered_file} -> {destination}")


@app.command()
def apply(
    config: ConfigPath,
    target: TargetPath,
    output: OutputPath = Path(".rendered"),
    execute: ExecuteFlag = False,
) -> None:
    """Validate, render, deploy and reconcile changed services."""
    inventory = _load(config)
    rendered = render_inventory(inventory, output_dir=output, template_root=_template_root())

    changed: list[tuple[InstanceSpec, Path, Path]] = []
    by_quadlet = {instance.quadlet_path: instance for instance in inventory.instances}

    for rendered_file in rendered:
        instance = by_quadlet[rendered_file.relative_to(output).as_posix()]
        destination = target.expanduser() / rendered_file.relative_to(output)
        current_text = destination.read_text(encoding="utf-8") if destination.exists() else ""
        rendered_text = rendered_file.read_text(encoding="utf-8")
        if current_text != rendered_text:
            changed.append((instance, rendered_file, destination))

    typer.echo(
        f"Apply plan for cluster '{inventory.cluster.name}' ({inventory.cluster.mode}): "
        f"{len(changed)}/{len(inventory.instances)} instance(s) changed"
    )

    for instance, rendered_file, destination in changed:
        typer.echo(
            f" - {instance.name} [{instance.role}/{instance.profile}] "
            f"{rendered_file} -> {destination}"
        )

    if not execute:
        for instance, _, _ in changed:
            for action in _prepare_runtime_mounts(instance, execute=False):
                typer.echo(action)
            for action in _repair_runtime_state_file(instance, execute=False):
                typer.echo(action)
            if instance.backup_policy.enabled and instance.backup_policy.pre_mutation:
                archive = backup_instance(
                    instance,
                    output_dir=Path(".backups/instances"),
                    execute=False,
                )
                typer.echo(f"DRY RUN backup plan for {instance.name}: {archive}")
        typer.echo("DRY RUN apply complete. Re-run with --execute to mutate state.")
        return

    service = SystemdService()
    failed = False
    restart_targets: list[str] = []

    for instance, rendered_file, destination in changed:
        for action in _prepare_runtime_mounts(instance, execute=True):
            typer.echo(action)
        for action in _repair_runtime_state_file(instance, execute=True):
            typer.echo(action)

        if instance.backup_policy.enabled and instance.backup_policy.pre_mutation:
            archive = backup_instance(instance, output_dir=Path(".backups/instances"), execute=True)
            typer.echo(f"Backup created for {instance.name}: {archive}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered_file, destination)
        typer.echo(f"Deployed {rendered_file} -> {destination}")
        restart_targets.append(instance.name)

    auto_onboard_repairs: list[tuple[InstanceSpec, AutoOnboardPlan]] = []
    for instance in inventory.instances:
        if not instance.auto_onboard or not instance.auto_onboard.enabled:
            continue
        try:
            plan = build_auto_onboard_plan(instance)
        except AutoOnboardError as exc:
            raise typer.BadParameter(str(exc)) from exc

        if plan.missing_required_env:
            missing = ", ".join(plan.missing_required_env)
            raise typer.BadParameter(
                f"Missing required environment variables for auto-onboard instance '{instance.name}': {missing}"
            )

        needs_repair = _auto_onboard_needs_repair(instance, plan)
        if needs_repair:
            auto_onboard_repairs.append((instance, plan))

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

    if not changed and not auto_onboard_repairs:
        typer.echo("No rendered changes detected; daemon-reload completed.")

    if restart_targets:
        for instance_name in restart_targets:
            restart_result = service.restart(instance_name, execute=True)
            _print_result(restart_result)
            failed = failed or restart_result.return_code != 0

    if failed:
        raise typer.Exit(code=1)


@app.command()
def restart(instance: str, execute: ExecuteFlag = False) -> None:
    """Reload/restart a systemd user service."""
    service = SystemdService()
    result = service.restart(instance, execute=execute)
    _print_result(result)


@app.command()
def status(instance: str, execute: ExecuteFlag = False) -> None:
    """Inspect status for a service."""
    service = SystemdService()
    result = service.status(instance, execute=execute)
    _print_result(result)

    if execute and _status_needs_diagnostics(result):
        typer.secho("Recent journal entries for failure analysis:", fg="yellow", err=True)
        logs_result = _status_diagnostics(service, instance, execute=True)
        if logs_result is None:
            return
        _print_result(logs_result)


@app.command("status-cluster")
def status_cluster(
    config: ConfigPath,
    execute: ExecuteFlag = False,
    format: StatusFormat = "text",
) -> None:
    """Inspect status for all services in a cluster."""
    inventory = _load(config)
    service = SystemdService()
    rows: list[dict[str, object]] = []

    for instance in inventory.instances:
        result = service.status(instance.name, execute=execute)
        diagnostics = None
        if _status_needs_diagnostics(result):
            diagnostics = _status_diagnostics(service, instance.name, execute=execute)
        row = {
            "instance": instance.name,
            "role": instance.role,
            "profile": instance.profile,
            "state": _status_state(result, execute),
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
                f"- {row['instance']} [{row['role']}/{row['profile']}] "
                f"state={row['state']} rc={row['return_code']}"
            )
            diagnostics_summary = _diagnostic_summary(
                CommandResult(command=[], return_code=0, stdout=str(row["diagnostics"]), stderr="")
                if row["diagnostics"]
                else None
            )
            if diagnostics_summary:
                typer.echo(f"  cause: {diagnostics_summary}")

    if execute and any(int(row["return_code"]) != 0 for row in rows):
        raise typer.Exit(code=1)


@app.command()
def logs(
    instance: str,
    lines: Annotated[int, typer.Option("--lines")] = 100,
    execute: ExecuteFlag = False,
) -> None:
    """Collect logs for a service."""
    service = SystemdService()
    result = service.logs(instance, lines=lines, execute=execute)
    _print_result(result)


@app.command()
def backup(
    config: ConfigPath,
    instance: InstanceName,
    output: OutputPath = Path(".backups"),
    execute: ExecuteFlag = False,
) -> None:
    """Backup workspace/config/state for an instance."""
    inventory = _load(config)
    chosen = _instance_by_name(inventory, instance)
    archive = backup_instance(chosen, output_dir=output, execute=execute)
    if execute:
        typer.echo(f"Backup created: {archive}")
    else:
        typer.echo(f"DRY RUN backup would create: {archive}")


@app.command("auto-onboard")
def auto_onboard(
    config: ConfigPath,
    instance: InstanceName,
    execute: ExecuteFlag = False,
) -> None:
    """Resolve auto_onboard config and write openclaw.json for an instance."""
    inventory = _load(config)
    chosen = _instance_by_name(inventory, instance)

    try:
        plan = build_auto_onboard_plan(chosen)
    except AutoOnboardError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if plan.missing_required_env:
        missing = ", ".join(plan.missing_required_env)
        typer.secho(
            f"[ERROR] Missing required environment variables for {chosen.name}: {missing}",
            fg="red",
            bold=True,
            err=True,
        )
        raise typer.Exit(1)

    top_level_keys = ", ".join(sorted(plan.config.keys()))
    typer.echo(f"Auto-onboard plan for {chosen.name}")
    typer.echo(f" - source: {config}")
    typer.echo(f" - target: {plan.target_path}")
    typer.echo(f" - backup: {plan.backup_path}")
    typer.echo(f" - openclaw.json keys: {top_level_keys}")
    if plan.guardrails:
        typer.secho("Guardrails:", fg="yellow", err=True)
        for guardrail in plan.guardrails:
            typer.secho(f" - {guardrail}", fg="yellow", err=True)

    if not execute:
        typer.echo("DRY RUN auto-onboard complete. Re-run with --execute to write openclaw.json.")
        return

    write_auto_onboard_config(plan, execute=True)
    typer.echo(f"Auto-onboard wrote {plan.target_path}")


@app.command()
def upgrade(
    config: ConfigPath,
    instance: InstanceName,
    tag: TagValue = None,
    digest: DigestValue = None,
    execute: ExecuteFlag = False,
) -> None:
    """Perform a controlled upgrade by changing target image tag/digest."""
    inventory = _load(config)
    chosen = _instance_by_name(inventory, instance)

    plan = build_upgrade_plan(config, instance, next_tag=tag, next_digest=digest)
    typer.echo(
        f"Upgrade plan for {plan.instance}: "
        f"{plan.previous_tag}@{plan.previous_digest} -> {plan.next_tag}@{plan.next_digest}"
    )

    if chosen.backup_policy.enabled and chosen.backup_policy.pre_mutation:
        instance_backup = backup_instance(
            chosen,
            output_dir=Path(".backups/instances"),
            execute=execute,
        )
        if execute:
            typer.echo(f"Instance backup created: {instance_backup}")
        else:
            typer.echo(f"DRY RUN instance backup would create: {instance_backup}")

    if not execute:
        typer.echo("DRY RUN: no config changes written")
        return

    backup_path = backup_config(config, output_dir=Path(".backups/config"))
    applied = apply_upgrade(config, instance, next_tag=tag, next_digest=digest)
    typer.echo(f"Backed up config to {backup_path}")
    typer.echo(f"Applied upgrade to {applied.next_tag}@{applied.next_digest}")


@app.command()
def rollback(
    config: ConfigPath,
    instance: InstanceName,
    execute: ExecuteFlag = False,
) -> None:
    """Rollback an instance digest to known-good."""
    inventory = _load(config)
    chosen = _instance_by_name(inventory, instance)

    if chosen.backup_policy.enabled and chosen.backup_policy.pre_mutation:
        instance_backup = backup_instance(
            chosen,
            output_dir=Path(".backups/instances"),
            execute=execute,
        )
        if execute:
            typer.echo(f"Instance backup created: {instance_backup}")
        else:
            typer.echo(f"DRY RUN instance backup would create: {instance_backup}")

    if not execute:
        typer.echo("DRY RUN rollback requires --execute to mutate config")
        return

    backup_path = backup_config(config, output_dir=Path(".backups/config"))
    plan = rollback_to_known_good(config, instance)
    typer.echo(f"Backed up config to {backup_path}")
    typer.echo(
        f"Rolled back {plan.instance}: "
        f"{plan.previous_tag}@{plan.previous_digest} -> {plan.next_tag}@{plan.next_digest}"
    )


@app.command()
def teardown(
    config: ConfigPath,
    instance: OptionalInstanceName = None,
    execute: ExecuteFlag = False,
    force_image: ForceImageRemoval = False,
) -> None:
    """Remove managed services, containers, and images for one or all instances."""
    inventory = _load(config)
    selected = inventory.instances
    if instance is not None:
        selected = [_instance_by_name(inventory, instance)]

    if not selected:
        typer.echo("No matching instances selected for teardown")
        return

    host_map = {host.name: host for host in inventory.hosts}
    service = SystemdService()
    failed = False

    image_usage: dict[str, int] = {}
    selected_image_usage: dict[str, int] = {}
    for known_instance in inventory.instances:
        ref = image_ref(known_instance)
        image_usage[ref] = image_usage.get(ref, 0) + 1
    for chosen in selected:
        ref = image_ref(chosen)
        selected_image_usage[ref] = selected_image_usage.get(ref, 0) + 1

    typer.echo(
        f"Teardown plan for cluster '{inventory.cluster.name}': {len(selected)} instance(s) "
        f"(execute={execute}, force_image={force_image})"
    )

    for chosen in selected:
        host = host_map[chosen.host]
        quadlet_target = Path(host.quadlet_root).expanduser() / chosen.quadlet_path

        typer.echo(f"- Teardown {chosen.name} [{chosen.role}/{chosen.profile}]")
        results = [
            service.stop(chosen.name, execute=execute),
            service.disable(chosen.name, execute=execute),
            service.remove_quadlet(str(quadlet_target), execute=execute),
            service.remove_container(chosen.container_name, execute=execute),
        ]
        for result in results:
            _print_result(result)
            if result.return_code != 0 and not _is_tolerated_teardown_error(result):
                failed = True

    reload_result = service.daemon_reload(execute=execute)
    _print_result(reload_result)
    if reload_result.return_code != 0:
        failed = True

    for ref, selected_users in selected_image_usage.items():
        total_users = image_usage.get(ref, 0)
        if not force_image and selected_users < total_users:
            typer.secho(
                f"Skipping image removal for {ref}: still used by {total_users - selected_users} other instance(s). "
                "Use --force-image to override.",
                fg="yellow",
                err=True,
            )
            continue

        result = service.remove_image(ref, execute=execute)
        _print_result(result)
        if result.return_code != 0 and not _is_tolerated_teardown_error(result):
            failed = True

    if not execute:
        typer.echo("DRY RUN teardown complete. Re-run with --execute to mutate state.")
        return

    if failed:
        raise typer.Exit(code=1)


app.command("remove")(teardown)


if __name__ == "__main__":
    app()
