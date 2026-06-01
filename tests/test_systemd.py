import pytest

from clawake.services.systemd import SystemdService


def test_rejects_invalid_instance_name() -> None:
    service = SystemdService()
    with pytest.raises(ValueError):
        service.unit_name("bad;name")
