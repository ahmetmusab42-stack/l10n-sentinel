from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .storage import ProjectRepository


def create_backup(
    repository: ProjectRepository,
    destination: Path,
    *,
    project_slug: str | None = None,
) -> Path:
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    repository.integrity_check()
    manifest = {
        "schema": 1,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "database": str(repository.path.name),
        "project_slug": project_slug,
    }
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    os.close(file_descriptor)
    temporary_archive = Path(temporary_name)
    try:
        with tempfile.TemporaryDirectory(dir=destination.parent) as snapshot_directory:
            snapshot_path = Path(snapshot_directory) / repository.path.name
            source = sqlite3.connect(repository.path)
            snapshot = sqlite3.connect(snapshot_path)
            try:
                source.backup(snapshot)
                snapshot.commit()
            finally:
                snapshot.close()
                source.close()
            with zipfile.ZipFile(
                temporary_archive,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                archive.write(snapshot_path, arcname=repository.path.name)
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )
                if project_slug:
                    archive.writestr(
                        f"projects/{project_slug}.json",
                        json.dumps(
                            repository.export_project_bundle(project_slug),
                            ensure_ascii=False,
                            indent=2,
                        ),
                    )
        os.replace(temporary_archive, destination)
    except Exception:
        temporary_archive.unlink(missing_ok=True)
        raise
    return destination


def restore_database(archive_path: Path, target_database: Path) -> Path:
    archive_path = Path(archive_path).expanduser().resolve()
    target_database = Path(target_database).expanduser().resolve()
    target_database.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        members = [item for item in archive.namelist() if item.endswith(".sqlite3")]
        if len(members) != 1:
            raise ValueError("backup archive must contain exactly one database")
        member = members[0]
        if Path(member).name != member or member.startswith(("/", "\\")):
            raise ValueError("backup database path is unsafe")
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=target_database.parent,
            prefix=f".{target_database.name}.",
            suffix=".restore",
        )
        temporary_database = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "wb") as output, archive.open(member) as source:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            connection = sqlite3.connect(temporary_database)
            try:
                result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                connection.close()
            if result != "ok":
                raise sqlite3.DatabaseError("restored database integrity check failed")
            os.replace(temporary_database, target_database)
        except Exception:
            temporary_database.unlink(missing_ok=True)
            raise
    return target_database
