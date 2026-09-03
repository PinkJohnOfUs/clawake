from pathlib import Path

from clawake.config import load_inventory
from clawake.services.render import (
    image_ref,
    render_instance,
    render_instance_assets,
    render_inventory,
)


def test_render_contains_expected_container_data() -> None:
    inventory = load_inventory(Path("examples/staff/team.yml"))
    instance = inventory.instances[0]
    rendered = render_instance(instance, template_root=Path("templates"))
    assert "ContainerName=excalibot-product-owner" in rendered
    assert f"Image={image_ref(instance)}" in rendered
    assert "UserNS=keep-id:uid=1000,gid=1000" in rendered
    assert "User=node" not in rendered
    assert "Label=clawake.role=product_owner" in rendered
    assert f"Volume={instance.workspace_path}:/workspace" in rendered
    assert f"Volume={instance.team_definition_path}:/team-definition:ro" in rendered
    assert f"Volume={instance.workspace_path}/.openclaw:/home/node/.openclaw" in rendered
    assert f"Network={instance.network_quadlet_path}" in rendered
    assert (
        "Exec=openclaw gateway run "
        f"--bind {instance.gateway_runtime.bind} "
        f"--port {instance.gateway_runtime.gateway_container_port} --allow-unconfigured"
    ) in rendered


def test_render_assets_include_container_network_and_volume() -> None:
    inventory = load_inventory(Path("examples/staff/team.yml"))
    instance = inventory.instances[0]
    rendered = render_instance_assets(instance, template_root=Path("templates"))

    assert instance.quadlet_path in rendered
    assert instance.network_quadlet_path in rendered
    assert instance.runtime_volume_quadlet_path in rendered

    network_text = rendered[instance.network_quadlet_path]
    volume_text = rendered[instance.runtime_volume_quadlet_path]
    assert "[Network]" in network_text
    assert f"NetworkName={instance.container_name}" in network_text
    assert "[Volume]" in volume_text
    assert f"Options=device={instance.workspace_path}/.openclaw" in volume_text


def test_browser_image_renders_writable_openclaw_cache_tmpfs() -> None:
    inventory = load_inventory(Path("examples/staff/team.yml"))
    instance = inventory.instances[0].model_copy(deep=True)
    instance.image.tag = "2026.8.2-browser"

    rendered = render_instance(instance, template_root=Path("templates"))

    assert "Volume=" in rendered
    assert "/.openclaw/cache/openclaw-1000:/home/node/.cache/openclaw-1000" in rendered


def test_render_inventory_writes_all_quadlet_artifacts(tmp_path: Path) -> None:
    inventory = load_inventory(Path("examples/staff/team.yml"))
    rendered_paths = render_inventory(
        inventory,
        output_dir=tmp_path,
        template_root=Path("templates"),
    )

    expected = {
        path for instance in inventory.instances for path in instance.quadlet_artifact_paths
    }
    assert expected == {str(path.relative_to(tmp_path)) for path in rendered_paths}
