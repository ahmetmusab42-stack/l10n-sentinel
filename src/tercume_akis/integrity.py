from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .models import LocalizationDocument, LocalizationEntry
from .qa import QAIssue, analyze_entries


@dataclass(slots=True, frozen=True)
class DocumentChange:
    key: str
    change_type: str
    severity: str
    explanation: str


def _entry_mapping(entry: LocalizationEntry) -> dict[str, str]:
    return {
        "source_key": entry.key,
        "source_text": entry.source_text,
        "target_text": entry.translation_text,
        "translation_status": entry.translation_status,
        "review_status": entry.review_status,
        "context": entry.context,
        "notes": entry.notes,
    }


def validate_document(document: LocalizationDocument) -> list[QAIssue]:
    issues = analyze_entries(_entry_mapping(entry) for entry in document.entries)
    if not document.entries:
        issues.append(
            QAIssue(
                key="<document>",
                issue_type="empty_document",
                severity="error",
                explanation="The localization document contains no entries.",
            )
        )
    for entry in document.entries:
        if not entry.key.strip():
            issues.append(
                QAIssue(
                    key="<empty-key>",
                    issue_type="empty_key",
                    severity="error",
                    explanation="A localization entry has an empty key.",
                )
            )
        if not entry.source_text.strip():
            issues.append(
                QAIssue(
                    key=entry.key or "<empty-key>",
                    issue_type="empty_source",
                    severity="error",
                    explanation="A localization entry has empty source text.",
                )
            )
    return issues


def _entries_by_key(
    entries: Iterable[LocalizationEntry],
) -> tuple[dict[str, LocalizationEntry], set[str]]:
    items = list(entries)
    counts = Counter(item.key for item in items)
    duplicates = {key for key, count in counts.items() if key and count > 1}
    return {item.key: item for item in items}, duplicates


def compare_documents(
    baseline: LocalizationDocument,
    current: LocalizationDocument,
) -> list[DocumentChange]:
    before, before_duplicates = _entries_by_key(baseline.entries)
    after, after_duplicates = _entries_by_key(current.entries)
    changes: list[DocumentChange] = []

    for key in sorted(before_duplicates | after_duplicates):
        changes.append(
            DocumentChange(
                key=key,
                change_type="duplicate_key",
                severity="error",
                explanation="The key is duplicated, so a reliable comparison is not possible.",
            )
        )

    duplicate_keys = before_duplicates | after_duplicates
    for key in sorted(set(before) - set(after) - duplicate_keys):
        changes.append(
            DocumentChange(
                key=key,
                change_type="removed",
                severity="warning",
                explanation="The source key was removed from the current document.",
            )
        )

    for key in sorted(set(after) - set(before) - duplicate_keys):
        changes.append(
            DocumentChange(
                key=key,
                change_type="added",
                severity="info",
                explanation="A new source key was added and may require translation.",
            )
        )

    for key in sorted(set(before) & set(after) - duplicate_keys):
        old = before[key]
        new = after[key]
        if old.source_text != new.source_text:
            changes.append(
                DocumentChange(
                    key=key,
                    change_type="source_changed",
                    severity="error",
                    explanation=(
                        "The source text changed; the existing translation must be reviewed."
                    ),
                )
            )
        if old.translation_text != new.translation_text:
            changes.append(
                DocumentChange(
                    key=key,
                    change_type="translation_changed",
                    severity="info",
                    explanation="The translation text changed.",
                )
            )

    return changes


def count_by_severity(
    items: Iterable[Mapping[str, Any] | QAIssue | DocumentChange],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        severity = item.get("severity") if isinstance(item, Mapping) else item.severity
        counts[str(severity)] += 1
    return dict(sorted(counts.items()))
