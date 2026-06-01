from __future__ import annotations

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


def _write_config(config_path: Path, config: dict) -> None:
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


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

    if image.get("digest"):
        image["known_good_digest"] = image["digest"]
    image["tag"] = plan.next_tag
    image["digest"] = plan.next_digest

    _write_config(config_path, config)
    return plan


def rollback_to_known_good(config_path: Path, instance_name: str) -> UpgradePlan:
    config = _load_config(config_path)
    instance = _find_instance(config, instance_name)
    image = instance["image"]
    known_good = image.get("known_good_digest")
    if not known_good:
        raise ValueError(f"Instance '{instance_name}' does not define image.known_good_digest")

    plan = _plan_from_image(instance_name, image, image["tag"], known_good)

    image["digest"] = known_good
    _write_config(config_path, config)
    return plan


def backup_config(config_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = output_dir / f"{config_path.stem}-{stamp}.yaml"
    backup_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path
