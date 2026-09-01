from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LocalizationEntry:
    key: str
    source_text: str
    translation_text: str = ""
    translation_status: str = "draft"
    review_status: str = "pending"
    context: str = ""
    notes: str = ""
    entry_id: str | None = None


@dataclass(slots=True)
class LocalizationDocument:
    project: dict[str, Any]
    entries: list[LocalizationEntry] = field(default_factory=list)
    glossary: list[dict[str, Any]] = field(default_factory=list)

    def to_bundle(self) -> dict[str, Any]:
        return {
            "project": dict(self.project),
            "entries": [
                {
                    "id": item.entry_id,
                    "source_key": item.key,
                    "source_text": item.source_text,
                    "target_text": item.translation_text,
                    "translation_status": item.translation_status,
                    "review_status": item.review_status,
                    "context": item.context,
                    "notes": item.notes,
                }
                for item in self.entries
            ],
            "glossary": [dict(item) for item in self.glossary],
        }

    @classmethod
    def from_bundle(cls, bundle: dict[str, Any]) -> LocalizationDocument:
        project = dict(bundle.get("project") or {})
        entries = [
            LocalizationEntry(
                entry_id=str(item.get("id")) if item.get("id") else None,
                key=str(item.get("source_key", "")),
                source_text=str(item.get("source_text", "")),
                translation_text=str(item.get("target_text", "")),
                translation_status=str(item.get("translation_status", "draft")),
                review_status=str(item.get("review_status", "pending")),
                context=str(item.get("context", "")),
                notes=str(item.get("notes", "")),
            )
            for item in bundle.get("entries", [])
            if isinstance(item, dict)
        ]
        glossary = [dict(item) for item in bundle.get("glossary", []) if isinstance(item, dict)]
        return cls(project=project, entries=entries, glossary=glossary)
