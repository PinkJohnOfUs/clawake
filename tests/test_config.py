from pathlib import Path

import pytest

from clawake.config import load_inventory


def test_load_example_inventory() -> None:
  inventory = load_inventory(Path("examples/staff/product.yml"))
  assert inventory.cluster.mode == "single_host"
  assert len(inventory.instances) == 2
  assert {instance.role for instance in inventory.instances} == {"product_owner", "developer"}
  assert all(instance.auto_onboard is not None for instance in inventory.instances)


def test_port_collision_validation(tmp_path: Path) -> None:
    collision = tmp_path / "collision.yaml"
    collision.write_text(
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
    workspace_path: /srv/a/one/workspace
    config_path: /srv/a/one/config
    state_path: /srv/a/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
    ports:
      - {bind_address: 127.0.0.1, host_port: 9010, container_port: 8080, protocol: tcp}
  - name: two
    host: a
    role: product_owner
    profile: public
    workspace_path: /srv/a/two/workspace
    config_path: /srv/a/two/config
    state_path: /srv/a/two/state
    quadlet_path: two.container
    container_name: two
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: Two}
    ports:
      - {bind_address: 127.0.0.1, host_port: 9010, container_port: 8080, protocol: tcp}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Port collision"):
        load_inventory(collision)


def test_tcp_udp_same_port_allowed(tmp_path: Path) -> None:
    cfg = tmp_path / "mixed-protocol.yaml"
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
    workspace_path: /srv/a/one/workspace
    config_path: /srv/a/one/config
    state_path: /srv/a/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
    ports:
      - {bind_address: 127.0.0.1, host_port: 9010, container_port: 8080, protocol: tcp}
  - name: two
    host: a
    role: product_owner
    profile: public
    workspace_path: /srv/a/two/workspace
    config_path: /srv/a/two/config
    state_path: /srv/a/two/state
    quadlet_path: two.container
    container_name: two
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: Two}
    ports:
      - {bind_address: 127.0.0.1, host_port: 9010, container_port: 8080, protocol: udp}
""",
        encoding="utf-8",
    )

    inventory = load_inventory(cfg)
    assert len(inventory.instances) == 2


def test_storage_path_collision_validation(tmp_path: Path) -> None:
    cfg = tmp_path / "collision-paths.yaml"
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
    workspace_path: /srv/shared/workspace
    config_path: /srv/a/one/config
    state_path: /srv/a/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
  - name: two
    host: a
    role: product_owner
    profile: public
    workspace_path: /srv/a/two/workspace
    config_path: /srv/shared/workspace
    state_path: /srv/a/two/state
    quadlet_path: two.container
    container_name: two
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: Two}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Path collision"):
        load_inventory(cfg)


def test_relative_workspace_path_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "relative-path.yaml"
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
    workspace_path: srv/a/one/workspace
    config_path: /srv/a/one/config
    state_path: /srv/a/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be an absolute path"):
        load_inventory(cfg)


def test_mount_source_colon_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "unsafe-mount.yaml"
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
    workspace_path: /srv/a/one/workspace
    config_path: /srv/a/one/config
    state_path: /srv/a/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    mounts:
      - {source: /srv/a:bad, target: /data}
    dashboard: {friendly_name: One}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not contain ':'"):
        load_inventory(cfg)


def test_gateway_runtime_requires_gateway_and_bridge_ports(tmp_path: Path) -> None:
    cfg = tmp_path / "gateway-runtime-missing-port.yaml"
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
    workspace_path: /srv/a/one/workspace
    config_path: /srv/a/one/config
    state_path: /srv/a/one/state
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    gateway_runtime:
      enabled: true
      bind: loopback
    ports:
      - {bind_address: 127.0.0.1, host_port: 9010, container_port: 18789, protocol: tcp}
    dashboard: {friendly_name: One}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing container ports"):
        load_inventory(cfg)


def test_workspace_root_env_expands_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "env-paths.yaml"
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
    workspace_path: ${CLAWAKE_WORKSPACE_ROOT}/examples/workspaces/dev
    config_path: ${CLAWAKE_WORKSPACE_ROOT}/examples/clawake-config/dev
    state_path: ${CLAWAKE_WORKSPACE_ROOT}/examples/clawake-state/dev
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWAKE_WORKSPACE_ROOT", "/tmp/project")

    inventory = load_inventory(cfg)
    instance = inventory.instances[0]
    assert instance.workspace_path == "/tmp/project/examples/workspaces/dev"
    assert instance.config_path == "/tmp/project/examples/clawake-config/dev"
    assert instance.state_path == "/tmp/project/examples/clawake-state/dev"
