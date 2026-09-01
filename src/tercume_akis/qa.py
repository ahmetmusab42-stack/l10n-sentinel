from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

PRINTF_PLACEHOLDER_PATTERN = re.compile(
    r"%(?!%)(?:\([^)]+\))?(?:\d+\$)?[-+#0 ']*(?:\d+|\*)?"
    r"(?:\.(?:\d+|\*))?[hlLzjt]*[diuoxXfFeEgGaAcspn]"
)
MUSTACHE_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
BRACE_PLACEHOLDER_PATTERN = re.compile(
    r"(?<!\{)\{\s*([A-Za-z_][A-Za-z0-9_.-]*|\d+)(?:\s*[,!:][^{}]*)?\}(?!\})"
)
MARKUP_TAG_PATTERN = re.compile(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9:_-]*)\b[^>]*?(/?)\s*>")
HTML_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass(slots=True)
class QAIssue:
    key: str
    issue_type: str
    severity: str
    explanation: str


def _placeholder_counts(text: str) -> Counter[str]:
    placeholders: list[str] = []
    placeholders.extend(match.group(0) for match in PRINTF_PLACEHOLDER_PATTERN.finditer(text))
    placeholders.extend(
        "{{" + match.group(1).strip() + "}}"
        for match in MUSTACHE_PLACEHOLDER_PATTERN.finditer(text)
    )
    placeholders.extend(
        "{" + match.group(1).strip() + "}"
        for match in BRACE_PLACEHOLDER_PATTERN.finditer(text)
    )
    return Counter(placeholders)


def _side_whitespace(text: str) -> tuple[bool, bool]:
    return bool(text[:1].isspace()) if text else False, bool(text[-1:].isspace()) if text else False


def _markup_tag_counts(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for match in MARKUP_TAG_PATTERN.finditer(text):
        closing, name, self_closing = match.groups()
        kind = "self" if self_closing else "close" if closing else "open"
        counts[f"{kind}:{name.lower()}"] += 1
    return counts


def _markup_is_balanced(text: str) -> bool:
    stack: list[str] = []
    for match in MARKUP_TAG_PATTERN.finditer(text):
        closing, raw_name, self_closing = match.groups()
        name = raw_name.lower()
        if self_closing or name in HTML_VOID_TAGS:
            continue
        if closing:
            if not stack or stack.pop() != name:
                return False
        else:
            stack.append(name)
    return not stack


def analyze_entries(entries: Iterable[Mapping[str, Any]]) -> list[QAIssue]:
    items = list(entries)
    issues: list[QAIssue] = []
    key_counts = Counter(str(item.get("source_key", "")) for item in items)

    for item in items:
        key = str(item.get("source_key", ""))
        source = str(item.get("source_text", ""))
        translation = str(item.get("target_text", ""))
        source_placeholders = _placeholder_counts(source)
        translation_placeholders = _placeholder_counts(translation)
        source_tags = _markup_tag_counts(source)
        translation_tags = _markup_tag_counts(translation)

        if not translation.strip():
            issues.append(
                QAIssue(
                    key=key,
                    issue_type="empty_translation",
                    severity="error",
                    explanation="Translation is empty.",
                )
            )
            if source.strip():
                issues.append(
                    QAIssue(
                        key=key,
                        issue_type="untranslated_entry",
                        severity="warning",
                        explanation="Entry has no translated text.",
                    )
                )

        source_clean = source.strip()
        translation_clean = translation.strip()
        if (
            source_clean
            and translation_clean
            and source_clean == translation_clean
        ):
            issues.append(
                QAIssue(
                    key=key,
                    issue_type="untranslated_entry",
                    severity="warning",
                    explanation="Translation matches the source text exactly.",
                )
            )

        if source_tags != translation_tags:
            issues.append(
                QAIssue(
                    key=key,
                    issue_type="markup_mismatch",
                    severity="error",
                    explanation="HTML/XML tag structure differs from the source text.",
                )
            )

        if _markup_is_balanced(source) and not _markup_is_balanced(translation):
            issues.append(
                QAIssue(
                    key=key,
                    issue_type="unbalanced_markup",
                    severity="error",
                    explanation="Target markup contains mismatched or unclosed tags.",
                )
            )

        source_left, source_right = _side_whitespace(source)
        translation_left, translation_right = _side_whitespace(translation)
        if (source_left, source_right) != (translation_left, translation_right):
            issues.append(
                QAIssue(
                    key=key,
                    issue_type="whitespace_difference",
                    severity="warning",
                    explanation="Leading or trailing whitespace differs from the source text.",
                )
            )

        if source.count("\n") != translation.count("\n"):
            issues.append(
                QAIssue(
                    key=key,
                    issue_type="newline_mismatch",
                    severity="warning",
                    explanation="Newline count differs from the source text.",
                )
            )

        missing = source_placeholders - translation_placeholders
        extra = translation_placeholders - source_placeholders
        if missing or extra:
            detail: list[str] = []
            if missing:
                missing_details = ", ".join(
                    f"{name} x{count}" for name, count in missing.items()
                )
                detail.append(f"missing: {missing_details}")
            if extra:
                extra_details = ", ".join(
                    f"{name} x{count}" for name, count in extra.items()
                )
                detail.append(f"extra: {extra_details}")
            issues.append(
                QAIssue(
                    key=key,
                    issue_type="placeholder_mismatch",
                    severity="error",
                    explanation="Placeholder mismatch detected (" + "; ".join(detail) + ").",
                )
            )

    for key, count in key_counts.items():
        if key and count > 1:
            issues.append(
                QAIssue(
                    key=key,
                    issue_type="duplicate_key",
                    severity="warning",
                    explanation="This translation key appears more than once.",
                )
            )

    return issues


def issue_counts(issues: Iterable[QAIssue]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for issue in issues:
        counts[issue.severity] += 1
    return dict(counts)
