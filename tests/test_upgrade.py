from pathlib import Path

import pytest
import yaml

from clawake.services.upgrade import apply_upgrade, build_upgrade_plan, rollback_to_known_good


def _load_image(config: Path, instance_name: str) -> dict[str, str]:
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    for instance in data["instances"]:
        if instance["name"] == instance_name:
            return instance["image"]
    raise AssertionError(f"Missing instance {instance_name}")


def test_build_upgrade_plan() -> None:
    config = Path("examples/staff/product.yml")
    image = _load_image(config, "openclaw-product-owner")
    plan = build_upgrade_plan(
        config,
        "openclaw-product-owner",
        next_tag="0.15.0",
        next_digest="sha256:abcd",
    )
    assert plan.previous_tag == image["tag"]
    assert plan.next_tag == "0.15.0"
    assert plan.next_digest == "sha256:abcd"


def test_apply_upgrade_and_rollback(tmp_path: Path) -> None:
    src = Path("examples/staff/product.yml")
    config = tmp_path / "product.yml"
    config.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    original_image = _load_image(config, "openclaw-product-owner")

    applied = apply_upgrade(
        config,
        "openclaw-product-owner",
        next_tag="0.15.0",
        next_digest="sha256:new",
    )
    assert applied.next_tag == "0.15.0"
    assert applied.next_digest == "sha256:new"

    rolled = rollback_to_known_good(config, "openclaw-product-owner")
    assert rolled.previous_digest == "sha256:new"
    assert rolled.next_digest == original_image["known_good_digest"]


def test_upgrade_plan_unknown_instance_raises() -> None:
    config = Path("examples/staff/product.yml")
    with pytest.raises(ValueError):
        build_upgrade_plan(config, "missing", next_tag=None, next_digest=None)
