from pathlib import Path

import pytest

from clawake.config import load_inventory


def test_load_example_inventory() -> None:
    inventory = load_inventory(Path("examples/inventory/dev.yaml"))
    assert inventory.cluster.mode == "single_host"
    assert len(inventory.instances) == 2
    assert {instance.role for instance in inventory.instances} == {"product_owner", "developer"}


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
