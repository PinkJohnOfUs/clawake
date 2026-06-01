from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from clawake.config import InstanceSpec, Inventory


def image_ref(instance: InstanceSpec) -> str:
    base = f"{instance.image.repository}:{instance.image.tag}"
    if instance.image.digest:
        return f"{base}@{instance.image.digest}"
    return base


def _environment(template_root: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_root)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_instance(instance: InstanceSpec, template_root: Path) -> str:
    env = _environment(template_root)
    template = env.get_template("quadlet/openclaw.container.j2")
    return template.render(instance=instance, image_ref=image_ref(instance)).strip() + "\n"


def render_inventory(inventory: Inventory, output_dir: Path, template_root: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered_paths: list[Path] = []
    for instance in inventory.instances:
        content = render_instance(instance, template_root=template_root)
        target = output_dir / instance.quadlet_path
        target.write_text(content, encoding="utf-8")
        rendered_paths.append(target)
    return rendered_paths
