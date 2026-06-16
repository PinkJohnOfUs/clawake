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
    workspace_path: /tmp/one/workspace
    team_definition_path: /tmp/one/role
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
    assert any("directly inside this instance" in message for message in plan.guardrails)
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
    workspace_path: /tmp/one/workspace
    team_definition_path: /tmp/one/role
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


def test_build_auto_onboard_plan_omits_missing_optional_env(tmp_path: Path) -> None:
    env_file = tmp_path / "i.env"
    env_file.write_text(
        "OPENCLAW_GATEWAY_BIND=local\nOPENCLAW_GATEWAY_TOKEN=test-token\n",
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
    workspace_path: /tmp/one/workspace
    team_definition_path: /tmp/one/role
    quadlet_path: one.container
    container_name: one
    image: {{repository: ghcr.io/x, tag: "1"}}
    env_files: [{env_file}]
    auto_onboard:
      required_env: [OPENCLAW_GATEWAY_BIND, OPENCLAW_GATEWAY_TOKEN]
      openclaw_config:
        gateway:
          mode: "$ENV:OPENCLAW_GATEWAY_BIND"
          auth:
            token: "$ENV:OPENCLAW_GATEWAY_TOKEN"
        channels:
          discord:
            token: "$ENV?:DISCORD_BOT_TOKEN"
    dashboard: {{friendly_name: One}}
""",
        encoding="utf-8",
    )

    plan = build_auto_onboard_plan(_load_instance(cfg))

    assert plan.missing_required_env == []
    assert plan.config["gateway"]["auth"]["token"] == "${OPENCLAW_GATEWAY_TOKEN}"
    assert plan.config["channels"]["discord"]["token"] == "${DISCORD_BOT_TOKEN}"


def test_build_auto_onboard_plan_keeps_sensitive_env_reference(tmp_path: Path) -> None:
    env_file = tmp_path / "i.env"
    env_file.write_text(
        "OPENCLAW_GATEWAY_BIND=local\nOPENCLAW_GATEWAY_TOKEN=test-token\n",
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
    workspace_path: /tmp/one/workspace
    team_definition_path: /tmp/one/role
    quadlet_path: one.container
    container_name: one
    image: {{repository: ghcr.io/x, tag: "1"}}
    env_files: [{env_file}]
    auto_onboard:
      required_env: [OPENCLAW_GATEWAY_BIND, OPENCLAW_GATEWAY_TOKEN]
      openclaw_config:
        gateway:
          mode: "$ENV:OPENCLAW_GATEWAY_BIND"
          auth:
            token: "$ENV:OPENCLAW_GATEWAY_TOKEN"
    dashboard: {{friendly_name: One}}
""",
        encoding="utf-8",
    )

    plan = build_auto_onboard_plan(_load_instance(cfg))

    assert plan.missing_required_env == []
    assert plan.config["gateway"]["mode"] == "local"
    assert plan.config["gateway"]["auth"]["token"] == "${OPENCLAW_GATEWAY_TOKEN}"


def test_build_auto_onboard_plan_keeps_missing_optional_reference(tmp_path: Path) -> None:
    env_file = tmp_path / "i.env"
    env_file.write_text(
        "OPENCLAW_GATEWAY_BIND=local\nOPENCLAW_GATEWAY_TOKEN=test-token\n",
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
    workspace_path: /tmp/one/workspace
    team_definition_path: /tmp/one/role
    quadlet_path: one.container
    container_name: one
    image: {{repository: ghcr.io/x, tag: "1"}}
    env_files: [{env_file}]
    auto_onboard:
      required_env: [OPENCLAW_GATEWAY_BIND, OPENCLAW_GATEWAY_TOKEN]
      openclaw_config:
        channels:
          discord:
            channel_id: "$ENV?:DISCORD_CHANNEL_ID"
    dashboard: {{friendly_name: One}}
""",
        encoding="utf-8",
    )

    plan = build_auto_onboard_plan(_load_instance(cfg))

    assert plan.missing_required_env == []
    assert "channel_id" not in plan.config["channels"]["discord"]


def test_write_auto_onboard_config_merges_existing_payload(tmp_path: Path) -> None:
    target_dir = tmp_path / "cfg"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "openclaw.json"
    target_file.write_text(
        json.dumps(
            {
                "channels": {
                    "discord": {
                        "groupPolicy": "allowlist",
                        "guilds": {"147": {"channels": {"151": {"enabled": True}}}},
                    }
                },
                "plugins": {"entries": {"discord": {"enabled": True}}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    from clawake.services.onboarding import AutoOnboardPlan

    plan = AutoOnboardPlan(
        instance="one",
        target_path=target_file,
        backup_path=target_dir / "openclaw.json.last-good",
        config={
            "gateway": {
                "mode": "local",
                "auth": {"token": "dev-product-owner-token"},
            },
            "channels": {"discord": {"token": "discord-token"}},
        },
        missing_required_env=[],
    )

    write_auto_onboard_config(plan, execute=True)

    payload = json.loads(plan.target_path.read_text(encoding="utf-8"))
    assert payload["gateway"]["mode"] == "local"
    assert payload["gateway"]["auth"]["token"] == "dev-product-owner-token"
    assert payload["channels"]["discord"]["token"] == "discord-token"
    assert payload["channels"]["discord"]["groupPolicy"] == "allowlist"
    assert payload["channels"]["discord"]["guilds"]["147"]["channels"]["151"]["enabled"] is True
    assert payload["plugins"]["entries"]["discord"]["enabled"] is True


def test_build_auto_onboard_plan_normalizes_discord_ids_to_guild_structure(tmp_path: Path) -> None:
    env_file = tmp_path / "i.env"
    env_file.write_text(
        "\n".join(
            [
                "OPENCLAW_GATEWAY_BIND=local",
                "OPENCLAW_GATEWAY_TOKEN=test-token",
                "DISCORD_SERVER_ID=1475244093541191822",
                "DISCORD_CHANNEL_ID=1514256860654600374",
            ]
        )
        + "\n",
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
    workspace_path: /tmp/one/workspace
    team_definition_path: /tmp/one/role
    quadlet_path: one.container
    container_name: one
    image: {{repository: ghcr.io/x, tag: "1"}}
    env_files: [{env_file}]
    auto_onboard:
      required_env: [OPENCLAW_GATEWAY_BIND, OPENCLAW_GATEWAY_TOKEN]
      openclaw_config:
        channels:
          discord:
            token: "$ENV?:DISCORD_BOT_TOKEN"
            server_id: "$ENV?:DISCORD_SERVER_ID"
            channel_id: "$ENV?:DISCORD_CHANNEL_ID"
    dashboard: {{friendly_name: One}}
""",
        encoding="utf-8",
    )

    plan = build_auto_onboard_plan(_load_instance(cfg))

    discord = plan.config["channels"]["discord"]
    assert "server_id" not in discord
    assert "channel_id" not in discord
    assert discord["guilds"]["1475244093541191822"]["channels"]["1514256860654600374"] == {
        "enabled": True,
        "requireMention": False,
    }


def test_build_auto_onboard_plan_drops_incomplete_discord_helper_fields(tmp_path: Path) -> None:
    env_file = tmp_path / "i.env"
    env_file.write_text(
        "\n".join(
            [
                "OPENCLAW_GATEWAY_BIND=local",
                "OPENCLAW_GATEWAY_TOKEN=test-token",
                "DISCORD_SERVER_ID=1475244093541191822",
            ]
        )
        + "\n",
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
    workspace_path: /tmp/one/workspace
    team_definition_path: /tmp/one/role
    quadlet_path: one.container
    container_name: one
    image: {{repository: ghcr.io/x, tag: "1"}}
    env_files: [{env_file}]
    auto_onboard:
      required_env: [OPENCLAW_GATEWAY_BIND, OPENCLAW_GATEWAY_TOKEN]
      openclaw_config:
        channels:
          discord:
            server_id: "$ENV?:DISCORD_SERVER_ID"
            channel_id: "$ENV?:DISCORD_CHANNEL_ID"
    dashboard: {{friendly_name: One}}
""",
        encoding="utf-8",
    )

    plan = build_auto_onboard_plan(_load_instance(cfg))

    discord = plan.config["channels"]["discord"]
    assert "server_id" not in discord
    assert "channel_id" not in discord
    assert "guilds" not in discord
