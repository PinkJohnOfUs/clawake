from __future__ import annotations

import tarfile
from datetime import UTC, datetime
from pathlib import Path

from clawake.config import InstanceSpec


def backup_instance(instance: InstanceSpec, output_dir: Path, execute: bool = False) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_path = output_dir / f"{instance.name}-{stamp}.tar.gz"

    if not execute:
        return archive_path

    with tarfile.open(archive_path, "w:gz") as archive:
        for idx, mount in enumerate(instance.mounts, start=1):
            source = Path(mount.source).expanduser()
            if source.exists():
                mount_identifier = mount.target.strip("/").replace("/", "__") or source.name
                archive.add(source, arcname=f"{idx:02d}__{mount_identifier}__{source.name}")

    return archive_path
