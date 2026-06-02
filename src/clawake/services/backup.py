from __future__ import annotations

import tarfile
from datetime import UTC, datetime
from pathlib import Path

from clawake.config import InstanceSpec


def backup_sources(instance: InstanceSpec) -> list[Path]:
    ordered = [
        Path(instance.workspace_path).expanduser(),
        Path(instance.config_path).expanduser(),
        Path(instance.state_path).expanduser(),
    ]
    ordered.extend(Path(path).expanduser() for path in instance.backup_policy.paths)

    unique: list[Path] = []
    seen: set[str] = set()
    for source in ordered:
        key = str(source)
        if key not in seen:
            seen.add(key)
            unique.append(source)
    return unique


def backup_instance(instance: InstanceSpec, output_dir: Path, execute: bool = False) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_path = output_dir / f"{instance.name}-{stamp}.tar.gz"

    if not execute:
        return archive_path

    with tarfile.open(archive_path, "w:gz") as archive:
        for idx, source in enumerate(backup_sources(instance), start=1):
            if source.exists():
                mount_identifier = source.name or f"path_{idx}"
                archive.add(source, arcname=f"{idx:02d}__{mount_identifier}")

    return archive_path
