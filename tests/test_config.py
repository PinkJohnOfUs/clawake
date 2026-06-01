from pathlib import Path

import pytest

from clawake.config import load_inventory


def test_load_example_inventory() -> None:
    inventory = load_inventory(Path("examples/inventory/dev.yaml"))
    assert inventory.instances[0].name == "openclaw-dev"


def test_port_collision_validation(tmp_path: Path) -> None:
    collision = tmp_path / "collision.yaml"
    collision.write_text(
        """
version: 1
hosts:
  - name: a
instances:
  - name: one
    host: a
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
    ports:
      - {bind_address: 127.0.0.1, host_port: 9010, container_port: 8080, protocol: tcp}
  - name: two
    host: a
    quadlet_path: two.container
    container_name: two
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: Two}
    ports:
      - {bind_address: 127.0.0.1, host_port: 9010, container_port: 8080, protocol: tcp}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_inventory(collision)


def test_tcp_udp_same_port_allowed(tmp_path: Path) -> None:
    cfg = tmp_path / "mixed-protocol.yaml"
    cfg.write_text(
        """
version: 1
hosts:
  - name: a
instances:
  - name: one
    host: a
    quadlet_path: one.container
    container_name: one
    image: {repository: ghcr.io/x, tag: "1"}
    dashboard: {friendly_name: One}
    ports:
      - {bind_address: 127.0.0.1, host_port: 9010, container_port: 8080, protocol: tcp}
  - name: two
    host: a
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
