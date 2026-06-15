from pathlib import Path

from clawake.config import load_inventory
from clawake.services.render import image_ref
from clawake.services.render import render_instance


def test_render_contains_expected_container_data() -> None:
    inventory = load_inventory(Path("examples/staff/product.yml"))
    instance = inventory.instances[0]
    rendered = render_instance(instance, template_root=Path("templates"))
    assert "ContainerName=excalibot-product-owner" in rendered
    assert f"Image={image_ref(instance)}" in rendered
    assert "UserNS=keep-id:uid=1000,gid=1000" in rendered
    assert "User=node" not in rendered
    assert "Label=clawake.role=product_owner" in rendered
    assert "Label=clawake.profile=public" in rendered
    assert "/examples/workspaces/product-owner:/workspace" in rendered
    assert "/openclaw.json:/home/node/.openclaw-public/openclaw.json" not in rendered
    assert f"{instance.state_path}:/home/node/.openclaw-public" in rendered
    assert (
        f"{instance.state_path}/workspace-public:/home/node/.openclaw/workspace-public"
        in rendered
    )
    assert "Exec=openclaw --profile public gateway run --bind loopback --port 18789" in rendered
