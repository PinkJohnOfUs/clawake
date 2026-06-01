from pathlib import Path

from clawake.config import load_inventory
from clawake.services.render import render_instance


def test_render_contains_expected_container_data() -> None:
    inventory = load_inventory(Path("examples/inventory/dev.yaml"))
    rendered = render_instance(
        inventory.instances[0],
        template_root=Path("templates"),
    )
    assert "ContainerName=openclaw-dev" in rendered
    assert "Image=ghcr.io/openclaw/gateway:0.14.0@sha256:" in rendered
