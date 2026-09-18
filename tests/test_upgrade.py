from pathlib import Path

import pytest
import yaml

from clawake.services.upgrade import (
    apply_upgrade,
    build_upgrade_plan,
    rollback_to_known_good,
)

PRODUCT_OWNER_INSTANCE = "excalibot-product-owner"


def _load_image(config: Path, instance_name: str) -> dict[str, str]:
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    for instance in data["instances"]:
        if instance["name"] == instance_name:
            return instance["image"]
    raise AssertionError(f"Missing instance {instance_name}")


def test_build_upgrade_plan() -> None:
    config = Path("examples/staff/team.yml")
    image = _load_image(config, PRODUCT_OWNER_INSTANCE)
    plan = build_upgrade_plan(
        config,
        PRODUCT_OWNER_INSTANCE,
        next_tag="0.15.0",
        next_digest="sha256:abcd",
    )
    assert plan.previous_tag == image["tag"]
    assert plan.next_tag == "0.15.0"
    assert plan.next_digest == "sha256:abcd"


def test_apply_upgrade_and_rollback(tmp_path: Path) -> None:
    src = Path("examples/staff/team.yml")
    config = tmp_path / "product.yml"
    config.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    # Keep this test independent from staff example defaults.
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    for instance in data["instances"]:
        if instance["name"] == PRODUCT_OWNER_INSTANCE:
            instance["image"]["known_good_digest"] = "sha256:known-good"
            break
    config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    original_image = _load_image(config, PRODUCT_OWNER_INSTANCE)

    applied = apply_upgrade(
        config,
        PRODUCT_OWNER_INSTANCE,
        next_tag="0.15.0",
        next_digest="sha256:new",
    )
    assert applied.next_tag == "0.15.0"
    assert applied.next_digest == "sha256:new"

    rolled = rollback_to_known_good(config, PRODUCT_OWNER_INSTANCE)
    assert rolled.previous_digest == "sha256:new"
    assert rolled.next_digest == original_image["known_good_digest"]
    assert rolled.next_tag == original_image["tag"]
    rolled_image = _load_image(config, PRODUCT_OWNER_INSTANCE)
    assert rolled_image["tag"] == original_image["tag"]


def test_upgrade_plan_unknown_instance_raises() -> None:
    config = Path("examples/staff/team.yml")
    with pytest.raises(ValueError):
        build_upgrade_plan(config, "missing", next_tag=None, next_digest=None)


def test_apply_upgrade_preserves_unrelated_yaml_formatting(tmp_path: Path) -> None:
    config = tmp_path / "team.yml"
    config.write_text(
        """instances:
  - name: one
    image:
      repository: ghcr.io/openclaw/openclaw
      tag: "old"
      digest: sha256:old
    dashboard:
      tags: [one, two]

  - name: two
    image:
      repository: example.invalid/two
      tag: "untouched"
""",
        encoding="utf-8",
    )

    apply_upgrade(config, "one", "new", "sha256:new")

    updated = config.read_text(encoding="utf-8")
    assert '      tag: "new"\n' in updated
    assert '      known_good_tag: "old"\n' in updated
    assert "      known_good_digest: sha256:old\n" in updated
    assert "      tags: [one, two]\n" in updated
    assert '      tag: "untouched"\n' in updated
