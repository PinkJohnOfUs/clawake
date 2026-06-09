from pathlib import Path

from clawake.config import load_inventory
from clawake.services.render import image_ref
from clawake.services.render import render_instance


def test_render_contains_expected_container_data() -> None:
    inventory = load_inventory(Path("examples/staff/product.yml"))
    instance = inventory.instances[0]
    rendered = render_instance(instance, template_root=Path("templates"))
    assert "ContainerName=openclaw-product-owner" in rendered
    assert f"Image={image_ref(instance)}" in rendered
    assert "Label=clawake.role=product_owner" in rendered
    assert "Label=clawake.profile=public" in rendered
    assert "/examples/workspaces/product-owner:/workspace" in rendered
    assert "/examples/clawake-config/product-owner/openclaw.json:/home/node/.openclaw-public/openclaw.json" in rendered
    assert "/examples/clawake-state/product-owner:/home/node/.openclaw-public" in rendered
    assert "Exec=openclaw --profile public gateway run --bind lan --port 18789" in rendered
