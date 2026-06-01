from pathlib import Path

import pytest

from clawake.services.upgrade import apply_upgrade, build_upgrade_plan, rollback_to_known_good


def test_build_upgrade_plan() -> None:
    config = Path("examples/inventory/dev.yaml")
    plan = build_upgrade_plan(config, "openclaw-dev", next_tag="0.15.0", next_digest="sha256:abcd")
    assert plan.previous_tag == "0.14.0"
    assert plan.next_tag == "0.15.0"
    assert plan.next_digest == "sha256:abcd"


def test_apply_upgrade_and_rollback(tmp_path: Path) -> None:
    src = Path("examples/inventory/dev.yaml")
    config = tmp_path / "dev.yaml"
    config.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    applied = apply_upgrade(config, "openclaw-dev", next_tag="0.15.0", next_digest="sha256:new")
    assert applied.next_tag == "0.15.0"
    assert applied.next_digest == "sha256:new"

    rolled = rollback_to_known_good(config, "openclaw-dev")
    assert rolled.previous_digest == "sha256:new"
    assert rolled.next_digest.startswith("sha256:111111")


def test_upgrade_plan_unknown_instance_raises() -> None:
    config = Path("examples/inventory/dev.yaml")
    with pytest.raises(ValueError):
        build_upgrade_plan(config, "missing", next_tag=None, next_digest=None)
