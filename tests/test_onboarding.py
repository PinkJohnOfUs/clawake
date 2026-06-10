import json
from pathlib import Path

import pytest

from clawake.config import load_inventory
from clawake.services.onboarding import (
    AutoOnboardError,
    build_auto_onboard_plan,
    write_auto_onboard_config,
)


def _load_instance(cfg: Path):
    inventory = load_inventory(cfg)
    return inventory.instances[0]


def test_build_auto_onboard_plan_resolves_env_templates(tmp_path: Path) -> None:
    env_file = tmp_path / "i.env"
    env_file.write_text(
        "OPENCLAW_MODEL_PROVIDER=openai\nOPENCLAW_MODEL=gpt-5.3-codex\n",
        encoding="utf-8",
    )

    cfg = tmp_path / "staff.yml"
    cfg.write_text(
        f"""
version: 1
cluster:
  name: c
  mode: single_host
  primary_host: a
hosts:
  - name: a
instances:
  - name: one
    host: a
    role: developer
    profile: internal
    workspace_path: /tmp/one/workspace
    config_path: /tmp/one/config
    state_path: /tmp/one/state
    quadlet_path: one.container
    container_name: one
    image: {{repository: ghcr.io/x, tag: "1"}}
    env_files: [{env_file}]
    auto_onboard:
      required_env: [OPENCLAW_MODEL_PROVIDER, OPENCLAW_MODEL]
      openclaw_config:
        model:
          provider: "$ENV:OPENCLAW_MODEL_PROVIDER"
          name: "$ENV:OPENCLAW_MODEL"
    dashboard: {{friendly_name: One}}
""",
        encoding="utf-8",
    )

    plan = build_auto_onboard_plan(_load_instance(cfg))

    assert plan.missing_required_env == []
    assert plan.config["model"]["provider"] == "openai"
    assert plan.config["model"]["name"] == "gpt-5.3-codex"
    assert any("--profile internal" in message for message in plan.guardrails)
    assert any("models auth login --provider openai --device-code" in message for message in plan.guardrails)


def test_build_auto_onboard_plan_raises_when_missing_config(tmp_path: Path) -> None:
    cfg = tmp_path / "staff.yml"
    cfg.write_text(
        """
version: 1
cluster:
  name: c
  mode: single_host
  primary_host: a
hosts:
  - name: a
instances:
  - name: one
    host: a
    role: developer
    profile: internal
    workspace_path: /tmp/one/workspace
    config_path: /tmp/one/config
    state_path: /tmp/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
""",
        encoding="utf-8",
    )

    with pytest.raises(AutoOnboardError, match="does not define auto_onboard"):
        build_auto_onboard_plan(_load_instance(cfg))


def test_write_auto_onboard_config_creates_backup(tmp_path: Path) -> None:
    target_dir = tmp_path / "cfg"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "openclaw.json"
    target_file.write_text('{"gateway": {"mode": "local"}}\n', encoding="utf-8")

    from clawake.services.onboarding import AutoOnboardPlan

    plan = AutoOnboardPlan(
        instance="one",
        target_path=target_file,
        backup_path=target_dir / "openclaw.json.last-good",
        config={"model": {"provider": "openai"}},
        missing_required_env=[],
    )

    write_auto_onboard_config(plan, execute=True)

    assert plan.backup_path.exists()
    payload = json.loads(plan.target_path.read_text(encoding="utf-8"))
    assert payload["model"]["provider"] == "openai"
