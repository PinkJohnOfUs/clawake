from __future__ import annotations

import difflib
import logging
import shutil
from pathlib import Path
from typing import Annotated

import typer

from clawake.config import InstanceSpec, Inventory, load_inventory
from clawake.services.backup import backup_instance
from clawake.services.render import render_instance, render_inventory
from clawake.services.systemd import SystemdService
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


def _load(path: Path) -> Inventory:
    return load_inventory(path)


def _template_root() -> Path:
    return Path(__file__).resolve().parents[2] / "templates"


def _instance_by_name(inventory: Inventory, name: str) -> InstanceSpec:
    for instance in inventory.instances:
        if instance.name == name:
            return instance
    raise typer.BadParameter(f"Unknown instance '{name}'")


@app.command()
def validate(config: ConfigPath) -> None:
    """Validate inventory configuration."""
    _load(config)
    typer.echo(f"OK: {config} is valid")


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
def restart(instance: str, execute: ExecuteFlag = False) -> None:
    """Reload/restart a systemd user service."""
    service = SystemdService()
    result = service.restart(instance, execute=execute)
    typer.echo(f"$ {' '.join(result.command)}")
    if result.stdout:
        typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr)


@app.command()
def status(instance: str, execute: ExecuteFlag = False) -> None:
    """Inspect status for a service."""
    service = SystemdService()
    result = service.status(instance, execute=execute)
    typer.echo(f"$ {' '.join(result.command)}")
    if result.stdout:
        typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr)


@app.command()
def logs(
    instance: str,
    lines: Annotated[int, typer.Option("--lines")] = 100,
    execute: ExecuteFlag = False,
) -> None:
    """Collect logs for a service."""
    service = SystemdService()
    result = service.logs(instance, lines=lines, execute=execute)
    typer.echo(f"$ {' '.join(result.command)}")
    if result.stdout:
        typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr)


@app.command()
def backup(
    config: ConfigPath,
    instance: InstanceName,
    output: OutputPath = Path(".backups"),
    execute: ExecuteFlag = False,
) -> None:
    """Backup workspace/config mounts for an instance."""
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
    plan = build_upgrade_plan(config, instance, next_tag=tag, next_digest=digest)
    typer.echo(
        f"Upgrade plan for {plan.instance}: "
        f"{plan.previous_tag}@{plan.previous_digest} -> {plan.next_tag}@{plan.next_digest}"
    )
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
