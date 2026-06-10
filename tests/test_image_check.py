import json
import subprocess
from typing import Any

import pytest

from clawake.config import ImageSpec
from clawake.services.image_check import ImageCheckError, check_image_availability


def _cp(stdout: str, return_code: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["podman", "manifest", "inspect"],
        returncode=return_code,
        stdout=stdout,
        stderr=stderr,
    )


def test_check_image_availability_strict_digest_tag_match(monkeypatch: pytest.MonkeyPatch) -> None:
    image = ImageSpec(
        repository="ghcr.io/openclaw/openclaw",
        tag="2026.6.5",
        digest="sha256:abc123",
    )

    manifest = {"schemaVersion": 2, "manifests": [{"digest": "sha256:abc123"}]}
    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _cp(stdout=json.dumps(manifest))

    monkeypatch.setattr("clawake.services.image_check.subprocess.run", _fake_run)

    check_image_availability(image)

    assert calls == [
        ["podman", "manifest", "inspect", "ghcr.io/openclaw/openclaw@sha256:abc123"],
        ["podman", "manifest", "inspect", "ghcr.io/openclaw/openclaw:2026.6.5"],
    ]


def test_check_image_availability_strict_digest_tag_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    image = ImageSpec(
        repository="ghcr.io/openclaw/openclaw",
        tag="2026.6.5",
        digest="sha256:abc123",
    )

    pinned = {"schemaVersion": 2, "manifests": [{"digest": "sha256:abc123"}]}
    tagged = {"schemaVersion": 2, "manifests": [{"digest": "sha256:def456"}]}

    def _fake_run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if cmd[-1].endswith("@sha256:abc123"):
            return _cp(stdout=json.dumps(pinned))
        return _cp(stdout=json.dumps(tagged))

    monkeypatch.setattr("clawake.services.image_check.subprocess.run", _fake_run)

    with pytest.raises(ImageCheckError) as exc_info:
        check_image_availability(image)

    assert "Tag and digest are inconsistent" in str(exc_info.value)
    assert "2026.6.5" in str(exc_info.value)
    assert "sha256:abc123" in str(exc_info.value)


def test_check_image_availability_tag_only(monkeypatch: pytest.MonkeyPatch) -> None:
    image = ImageSpec(repository="ghcr.io/openclaw/openclaw", tag="2026.6.5")

    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _cp(stdout='{"schemaVersion":2}')

    monkeypatch.setattr("clawake.services.image_check.subprocess.run", _fake_run)

    check_image_availability(image)

    assert calls == [["podman", "manifest", "inspect", "ghcr.io/openclaw/openclaw:2026.6.5"]]
