from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from clawake.config import ImageSpec


@dataclass
class ImageCheckError(Exception):
    """Raised when an image cannot be verified or pulled from the registry."""

    image_ref: str
    reason: str
    hint: str = field(default="")

    def __str__(self) -> str:
        msg = f"Image check failed for '{self.image_ref}': {self.reason}"
        if self.hint:
            msg += f"\n  Fix: {self.hint}"
        return msg


def _classify_stderr(stderr: str) -> str:
    """Return an actionable hint based on the podman error output."""
    lower = stderr.lower()
    if "manifest unknown" in lower or "not found" in lower or "404" in lower:
        return (
            "Check that the image tag and digest are correct and the image exists in the registry."
        )
    if "unauthorized" in lower or "access denied" in lower or "forbidden" in lower or "403" in lower:
        return (
            "The registry refused access to this image reference. OpenClaw images are public and do not require "
            "podman login; verify the repository, tag, and digest, and confirm that the image is actually published "
            "in ghcr.io. The OpenClaw container images can be found here: "
            "https://github.com/openclaw/openclaw/pkgs/container/openclaw. If you intentionally changed the reference "
            "to a non-existent image, this error is expected."
        )
    if (
        "connection refused" in lower
        or "no route to host" in lower
        or "timeout" in lower
        or "dial tcp" in lower
        or "i/o timeout" in lower
    ):
        return "Network error. Check connectivity to the registry and any proxy or firewall settings."
    if "digest" in lower and ("mismatch" in lower or "invalid" in lower):
        return (
            "The image digest in the config does not match the registry. "
            "Update 'digest' in product.yml or verify the image has not been replaced."
        )
    return "Check the podman logs above for details."


def _build_image_ref(image_spec: ImageSpec) -> str:
    """Build the fully-qualified image reference, preferring digest-pinned form."""
    if image_spec.digest:
        return f"{image_spec.repository}@{image_spec.digest}"
    return f"{image_spec.repository}:{image_spec.tag}"


def check_image_availability(image_spec: ImageSpec, timeout: int = 30) -> None:
    """Verify the image is reachable via 'podman manifest inspect'.

    Raises ImageCheckError with a clear reason and actionable hint on failure.
    Does NOT pull the image; uses manifest inspection only (read-only, fast).
    """
    image_ref = _build_image_ref(image_spec)
    try:
        result = subprocess.run(
            ["podman", "manifest", "inspect", image_ref],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ImageCheckError(
            image_ref=image_ref,
            reason="'podman' binary not found.",
            hint="Install Podman (https://podman.io/getting-started/installation).",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ImageCheckError(
            image_ref=image_ref,
            reason=f"Timed out after {timeout}s while inspecting the image manifest.",
            hint="Check network connectivity to the registry or increase the timeout.",
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        hint = _classify_stderr(stderr)
        raise ImageCheckError(image_ref=image_ref, reason=stderr, hint=hint)
