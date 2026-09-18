from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml


@dataclass
class UpgradePlan:
    instance: str
    previous_tag: str
    previous_digest: str | None
    next_tag: str
    next_digest: str | None


def _load_config(config_path: Path) -> dict:
    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Failed to read config file {config_path}: {exc}") from exc

    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {config_path}: {exc}") from exc


def _find_instance(config: dict, instance_name: str) -> dict:
    for instance in config.get("instances", []):
        if instance.get("name") == instance_name:
            return instance
    raise ValueError(f"Unknown instance '{instance_name}'")


def _format_image_value(key: str, value: str) -> str:
    return json.dumps(value) if key.endswith("tag") else value


def _update_image_fields(config_path: Path, instance_name: str, updates: dict[str, str]) -> None:
    """Update one image mapping without reformatting the rest of the YAML document."""
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    instance_pattern = re.compile(r"^(\s*)-\s+name:\s*" + re.escape(instance_name) + r"\s*$")
    instance_start = next(
        (index for index, line in enumerate(lines) if instance_pattern.match(line.rstrip("\n"))),
        None,
    )
    if instance_start is None:
        raise ValueError(f"Unknown instance '{instance_name}'")

    instance_indent = len(lines[instance_start]) - len(lines[instance_start].lstrip())
    instance_end = len(lines)
    for index in range(instance_start + 1, len(lines)):
        stripped = lines[index].lstrip()
        indent = len(lines[index]) - len(stripped)
        if indent == instance_indent and stripped.startswith("- name:"):
            instance_end = index
            break

    image_index = next(
        (
            index
            for index in range(instance_start + 1, instance_end)
            if lines[index].strip() == "image:"
        ),
        None,
    )
    if image_index is None:
        raise ValueError(f"Instance '{instance_name}' does not define image")

    image_indent = len(lines[image_index]) - len(lines[image_index].lstrip())
    child_indent = image_indent + 2
    image_end = instance_end
    positions: dict[str, int] = {}
    field_pattern = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):")
    for index in range(image_index + 1, instance_end):
        stripped = lines[index].lstrip()
        if stripped and len(lines[index]) - len(stripped) <= image_indent:
            image_end = index
            break
        match = field_pattern.match(lines[index])
        if match and len(match.group(1)) == child_indent:
            positions[match.group(2)] = index

    for key, value in updates.items():
        rendered = f"{' ' * child_indent}{key}: {_format_image_value(key, value)}\n"
        if key in positions:
            lines[positions[key]] = rendered
        else:
            lines.insert(image_end, rendered)
            image_end += 1
            positions = {
                existing_key: existing_index + (1 if existing_index >= image_end - 1 else 0)
                for existing_key, existing_index in positions.items()
            }

    config_path.write_text("".join(lines), encoding="utf-8")


def _plan_from_image(
    instance_name: str,
    image: dict,
    next_tag: str | None,
    next_digest: str | None,
) -> UpgradePlan:
    return UpgradePlan(
        instance=instance_name,
        previous_tag=image["tag"],
        previous_digest=image.get("digest"),
        next_tag=next_tag or image["tag"],
        next_digest=next_digest if next_digest is not None else image.get("digest"),
    )


def build_upgrade_plan(
    config_path: Path,
    instance_name: str,
    next_tag: str | None,
    next_digest: str | None,
) -> UpgradePlan:
    config = _load_config(config_path)
    instance = _find_instance(config, instance_name)
    return _plan_from_image(instance_name, instance["image"], next_tag, next_digest)


def apply_upgrade(
    config_path: Path,
    instance_name: str,
    next_tag: str | None,
    next_digest: str | None,
) -> UpgradePlan:
    config = _load_config(config_path)
    instance = _find_instance(config, instance_name)
    image = instance["image"]

    plan = _plan_from_image(instance_name, image, next_tag, next_digest)

    updates = {
        "tag": plan.next_tag,
        "digest": plan.next_digest,
        "known_good_tag": image["tag"],
    }
    if image.get("digest"):
        updates["known_good_digest"] = image["digest"]

    _update_image_fields(config_path, instance_name, updates)
    return plan


def rollback_to_known_good(config_path: Path, instance_name: str) -> UpgradePlan:
    config = _load_config(config_path)
    instance = _find_instance(config, instance_name)
    image = instance["image"]
    known_good = image.get("known_good_digest")
    if not known_good:
        raise ValueError(f"Instance '{instance_name}' does not define image.known_good_digest")

    known_good_tag = image.get("known_good_tag")
    if not known_good_tag:
        raise ValueError(f"Instance '{instance_name}' does not define image.known_good_tag")

    plan = _plan_from_image(instance_name, image, known_good_tag, known_good)

    _update_image_fields(
        config_path,
        instance_name,
        {"tag": known_good_tag, "digest": known_good},
    )
    return plan


def backup_config(config_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = output_dir / f"{config_path.stem}-{stamp}.yaml"
    backup_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path
