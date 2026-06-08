from __future__ import annotations

import difflib
import json
import logging
import shutil
from pathlib import Path
from typing import Annotated, Literal

import typer

from clawake.config import InstanceSpec, Inventory, load_inventory
from clawake.services.backup import backup_instance
from clawake.services.render import render_instance, render_inventory
from clawake.services.systemd import CommandResult, SystemdService
from clawake.services.image_check import ImageCheckError, check_image_availability
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
TagValue = Annotated[str | None, typer.Option("--tag")]
DigestValue = Annotated[str | None, typer.Option("--digest")]
StatusFormat = Annotated[Literal["text", "json"], typer.Option("--format")]


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


@app.command()
def validate(config: ConfigPath) -> None:
    """Validate inventory configuration and verify image availability."""
    inventory = _load(config)

    errors: list[tuple[str, ImageCheckError]] = []
    for instance in inventory.instances:
        try:
            check_image_availability(instance.image)
        except ImageCheckError as exc:
            errors.append((instance.name, exc))

    if errors:
        typer.secho(f"Validation failed: {len(errors)} image check(s) failed", fg="red", bold=True, err=True)
        hints: list[str] = []
        for instance_name, exc in errors:
            hint = _enrich_public_image_hint(exc)
            _print_validation_failure(instance_name, exc)
            if hint not in hints:
                hints.append(hint)

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

    for instance, rendered_file, destination in changed:
        if instance.backup_policy.enabled and instance.backup_policy.pre_mutation:
            archive = backup_instance(instance, output_dir=Path(".backups/instances"), execute=True)
            typer.echo(f"Backup created for {instance.name}: {archive}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered_file, destination)
        typer.echo(f"Deployed {rendered_file} -> {destination}")

    if changed:
        reload_result = service.daemon_reload(execute=True)
        _print_result(reload_result)
        failed = failed or reload_result.return_code != 0

        for instance, _, _ in changed:
            restart_result = service.restart(instance.name, execute=True)
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
        row = {
            "instance": instance.name,
            "role": instance.role,
            "profile": instance.profile,
            "state": _status_state(result, execute),
            "return_code": result.return_code,
            "unit": service.unit_name(instance.name),
            "stdout": result.stdout,
            "stderr": result.stderr,
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


if __name__ == "__main__":
    app()
