from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash_event(
    *,
    event_id: str,
    occurred_at: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload_json: str,
    previous_hash: str,
) -> str:
    body = "\x1f".join(
        (event_id, occurred_at, action, entity_type, entity_id, payload_json, previous_hash)
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class ProjectRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    slug TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source_language TEXT NOT NULL,
                    target_language TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS translation_entries (
                    id TEXT PRIMARY KEY,
                    project_slug TEXT NOT NULL REFERENCES projects(slug) ON DELETE CASCADE,
                    source_key TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    target_text TEXT NOT NULL DEFAULT '',
                    translation_status TEXT NOT NULL CHECK(
                        translation_status IN ('draft', 'translated', 'review', 'done')
                    ),
                    review_status TEXT NOT NULL CHECK(
                        review_status IN ('pending', 'in-review', 'approved', 'rejected')
                    ),
                    context TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_slug, source_key)
                );
                CREATE TABLE IF NOT EXISTS glossary_terms (
                    id TEXT PRIMARY KEY,
                    project_slug TEXT NOT NULL REFERENCES projects(slug) ON DELETE CASCADE,
                    source_term TEXT NOT NULL,
                    target_term TEXT NOT NULL,
                    definition TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('active','deprecated')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_slug, source_term)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                """
            )

    def _ensure_project(self, project_slug: str) -> None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT slug FROM projects WHERE slug=?",
                (project_slug,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown project: {project_slug}")

    def _append_audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        payload: Mapping[str, Any],
        connection: sqlite3.Connection,
    ) -> None:
        prior = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        previous_hash = prior[0] if prior else "0" * 64
        event_id = str(uuid.uuid4())
        occurred_at = _utc_now()
        payload_json = _canonical_json(payload)
        digest = _hash_event(
            event_id=event_id,
            occurred_at=occurred_at,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload_json,
            previous_hash=previous_hash,
        )
        connection.execute(
            """
            INSERT INTO audit_events(
                event_id,
                occurred_at,
                action,
                entity_type,
                entity_id,
                payload_json,
                previous_hash,
                event_hash
            )
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                event_id,
                occurred_at,
                action,
                entity_type,
                entity_id,
                payload_json,
                previous_hash,
                digest,
            ),
        )

    def create_project(
        self,
        *,
        slug: str,
        name: str,
        source_language: str,
        target_language: str,
        description: str = "",
        overwrite: bool = False,
    ) -> str:
        slug = slug.strip().lower()
        name = name.strip()
        if not slug or not all(ch.isalnum() or ch == "-" for ch in slug):
            raise ValueError(
                "project slug must contain only lowercase letters, digits, and hyphens"
            )
        with self.transaction() as connection:
            if overwrite:
                connection.execute("DELETE FROM projects WHERE slug=?", (slug,))
            connection.execute(
                """
                INSERT INTO projects(
                    slug,
                    name,
                    source_language,
                    target_language,
                    description,
                    created_at,
                    updated_at
                )
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(slug) DO UPDATE SET
                    name=excluded.name,
                    source_language=excluded.source_language,
                    target_language=excluded.target_language,
                    description=excluded.description,
                    updated_at=excluded.updated_at
                """,
                (
                    slug,
                    name,
                    source_language.strip(),
                    target_language.strip(),
                    description.strip(),
                    _utc_now(),
                    _utc_now(),
                ),
            )
            self._append_audit(
                action="project.upserted",
                entity_type="project",
                entity_id=slug,
                payload={"slug": slug},
                connection=connection,
            )
        return slug

    def list_projects(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC, slug ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_slug: str) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE slug=?", (project_slug,)
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown project: {project_slug}")
        return dict(row)

    def get_entry_by_key(self, project_slug: str, source_key: str) -> dict[str, Any] | None:
        self._ensure_project(project_slug)
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM translation_entries WHERE project_slug=? AND source_key=?",
                (project_slug, source_key),
            ).fetchone()
        return dict(row) if row is not None else None

    def add_entry(
        self,
        *,
        project_slug: str,
        source_key: str,
        source_text: str,
        target_text: str = "",
        translation_status: str = "draft",
        review_status: str = "pending",
        context: str = "",
        notes: str = "",
    ) -> str:
        self._ensure_project(project_slug)
        entry_id = str(uuid.uuid4())
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO translation_entries(
                    id,
                    project_slug,
                    source_key,
                    source_text,
                    target_text,
                    translation_status,
                    review_status,
                    context,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    entry_id,
                    project_slug,
                    source_key.strip(),
                    source_text.strip(),
                    target_text.strip(),
                    translation_status,
                    review_status,
                    context.strip(),
                    notes.strip(),
                    _utc_now(),
                    _utc_now(),
                ),
            )
            self._append_audit(
                action="entry.added",
                entity_type="entry",
                entity_id=entry_id,
                payload={"project_slug": project_slug, "source_key": source_key},
                connection=connection,
            )
        return entry_id

    def upsert_entry(
        self,
        *,
        project_slug: str,
        source_key: str,
        source_text: str,
        target_text: str = "",
        translation_status: str = "draft",
        review_status: str = "pending",
        context: str = "",
        notes: str = "",
    ) -> str:
        existing = self.get_entry_by_key(project_slug, source_key)
        if existing is None:
            return self.add_entry(
                project_slug=project_slug,
                source_key=source_key,
                source_text=source_text,
                target_text=target_text,
                translation_status=translation_status,
                review_status=review_status,
                context=context,
                notes=notes,
            )
        self.update_entry(
            str(existing["id"]),
            source_text=source_text,
            target_text=target_text,
            translation_status=translation_status,
            review_status=review_status,
            context=context,
            notes=notes,
        )
        return str(existing["id"])

    def update_entry(
        self,
        entry_id: str,
        *,
        source_text: str | None = None,
        target_text: str | None = None,
        translation_status: str | None = None,
        review_status: str | None = None,
        context: str | None = None,
        notes: str | None = None,
    ) -> None:
        updates: list[str] = []
        values: list[Any] = []
        if source_text is not None:
            updates.append("source_text=?")
            values.append(source_text.strip())
        if target_text is not None:
            updates.append("target_text=?")
            values.append(target_text.strip())
        if translation_status is not None:
            updates.append("translation_status=?")
            values.append(translation_status)
        if review_status is not None:
            updates.append("review_status=?")
            values.append(review_status)
        if context is not None:
            updates.append("context=?")
            values.append(context.strip())
        if notes is not None:
            updates.append("notes=?")
            values.append(notes.strip())
        if not updates:
            return
        updates.append("updated_at=?")
        values.append(_utc_now())
        values.append(entry_id)
        with self.transaction() as connection:
            connection.execute(
                f"UPDATE translation_entries SET {', '.join(updates)} WHERE id=?",
                values,
            )
            self._append_audit(
                action="entry.updated",
                entity_type="entry",
                entity_id=entry_id,
                payload={"entry_id": entry_id},
                connection=connection,
            )

    def list_entries(
        self,
        project_slug: str,
        *,
        search: str | None = None,
        translation_status: str | None = None,
        review_status: str | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_project(project_slug)
        clauses = ["project_slug=?"]
        values: list[Any] = [project_slug]
        if search:
            clauses.append(
                "(source_key LIKE ? OR source_text LIKE ? OR target_text LIKE ? "
                "OR context LIKE ? OR notes LIKE ?)"
            )
            pattern = f"%{search.strip()}%"
            values.extend([pattern] * 5)
        if translation_status:
            clauses.append("translation_status=?")
            values.append(translation_status)
        if review_status:
            clauses.append("review_status=?")
            values.append(review_status)
        query = (
            "SELECT * FROM translation_entries WHERE "
            f"{' AND '.join(clauses)} ORDER BY updated_at DESC, source_key ASC"
        )
        with closing(self.connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [dict(row) for row in rows]

    def add_glossary_term(
        self,
        *,
        project_slug: str,
        source_term: str,
        target_term: str,
        definition: str = "",
        notes: str = "",
        status: str = "active",
    ) -> str:
        self._ensure_project(project_slug)
        term_id = str(uuid.uuid4())
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO glossary_terms(
                    id,
                    project_slug,
                    source_term,
                    target_term,
                    definition,
                    notes,
                    status,
                    created_at,
                    updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_slug, source_term) DO UPDATE SET
                    target_term=excluded.target_term,
                    definition=excluded.definition,
                    notes=excluded.notes,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    term_id,
                    project_slug,
                    source_term.strip(),
                    target_term.strip(),
                    definition.strip(),
                    notes.strip(),
                    status,
                    _utc_now(),
                    _utc_now(),
                ),
            )
            self._append_audit(
                action="glossary.upserted",
                entity_type="glossary",
                entity_id=term_id,
                payload={"project_slug": project_slug, "source_term": source_term},
                connection=connection,
            )
        return term_id

    def list_glossary_terms(
        self, project_slug: str, *, search: str | None = None
    ) -> list[dict[str, Any]]:
        self._ensure_project(project_slug)
        clauses = ["project_slug=?"]
        values: list[Any] = [project_slug]
        if search:
            clauses.append(
                "(source_term LIKE ? OR target_term LIKE ? OR definition LIKE ? "
                "OR notes LIKE ?)"
            )
            pattern = f"%{search.strip()}%"
            values.extend([pattern] * 4)
        with closing(self.connect()) as connection:
            rows = connection.execute(
                (
                    "SELECT * FROM glossary_terms WHERE "
                    f"{' AND '.join(clauses)} ORDER BY source_term ASC"
                ),
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def project_summary(self, project_slug: str) -> dict[str, Any]:
        project = self.get_project(project_slug)
        entries = self.list_entries(project_slug)
        glossary = self.list_glossary_terms(project_slug)
        return {
            "project": project,
            "entry_count": len(entries),
            "glossary_count": len(glossary),
            "draft_count": sum(1 for item in entries if item["translation_status"] == "draft"),
            "translated_count": sum(
                1 for item in entries if item["translation_status"] == "translated"
            ),
            "review_count": sum(1 for item in entries if item["review_status"] == "in-review"),
            "approved_count": sum(1 for item in entries if item["review_status"] == "approved"),
        }

    def export_project_bundle(self, project_slug: str) -> dict[str, Any]:
        return {
            "schema": 1,
            "exported_at": _utc_now(),
            "project": self.get_project(project_slug),
            "entries": self.list_entries(project_slug),
            "glossary": self.list_glossary_terms(project_slug),
        }

    def import_project_bundle(self, payload: Mapping[str, Any], *, replace: bool = False) -> str:
        project = payload.get("project")
        if not isinstance(project, Mapping):
            raise ValueError("project bundle is missing project data")
        slug = str(project.get("slug", "")).strip().lower()
        if not slug:
            raise ValueError("project slug is required")
        if replace:
            with self.transaction() as connection:
                connection.execute("DELETE FROM projects WHERE slug=?", (slug,))
        self.create_project(
            slug=slug,
            name=str(project.get("name", slug)),
            source_language=str(project.get("source_language", "")),
            target_language=str(project.get("target_language", "")),
            description=str(project.get("description", "")),
            overwrite=True,
        )
        for entry in payload.get("entries", []):
            if isinstance(entry, Mapping):
                self.add_entry(
                    project_slug=slug,
                    source_key=str(entry.get("source_key", "")),
                    source_text=str(entry.get("source_text", "")),
                    target_text=str(entry.get("target_text", "")),
                    translation_status=str(entry.get("translation_status", "draft")),
                    review_status=str(entry.get("review_status", "pending")),
                    context=str(entry.get("context", "")),
                    notes=str(entry.get("notes", "")),
                )
        for term in payload.get("glossary", []):
            if isinstance(term, Mapping):
                self.add_glossary_term(
                    project_slug=slug,
                    source_term=str(term.get("source_term", "")),
                    target_term=str(term.get("target_term", "")),
                    definition=str(term.get("definition", "")),
                    notes=str(term.get("notes", "")),
                    status=str(term.get("status", "active")),
                )
        return slug

    def integrity_check(self) -> None:
        with closing(self.connect()) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if result != "ok" or foreign_keys:
            raise sqlite3.DatabaseError("database integrity check failed")
