from __future__ import annotations

import json
import os
import tempfile
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .qa import analyze_entries

MAX_CATALOG_BYTES = 16 * 1024 * 1024
MAX_CATALOG_DEPTH = 64
MAX_CATALOG_MESSAGES = 100_000
MAX_MESSAGE_CHARACTERS = 1_000_000


@dataclass(slots=True, frozen=True)
class CatalogMessage:
    key: str
    text: str
    line: int


@dataclass(slots=True, frozen=True)
class CatalogFinding:
    key: str
    issue_type: str
    severity: str
    explanation: str
    path: str
    line: int


class _DuplicateKeyError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _pointer_part(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _line_for_key(lines: list[str], key: str, start: int) -> tuple[int, int]:
    marker = json.dumps(key, ensure_ascii=False)
    for index in range(start, len(lines)):
        if marker in lines[index]:
            return index + 1, index + 1
    for index, line in enumerate(lines):
        if marker in line:
            return index + 1, start
    return 1, start


def load_json_catalog(path: Path) -> list[CatalogMessage]:
    path = Path(path).expanduser().resolve()
    size = path.stat().st_size
    if size > MAX_CATALOG_BYTES:
        raise ValueError(
            f"catalog is {size} bytes; the safety limit is {MAX_CATALOG_BYTES} bytes"
        )
    text = path.read_text(encoding="utf-8-sig")
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except _DuplicateKeyError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except RecursionError as exc:
        raise ValueError("catalog nesting exceeds the JSON parser safety limit") from exc
    if not isinstance(payload, dict):
        raise ValueError("a locale catalog must be a JSON object")
    if "project" in payload and "entries" in payload:
        raise ValueError(
            "native L10n Sentinel project bundles are not locale catalogs; use validate instead"
        )

    messages: list[CatalogMessage] = []
    seen: set[str] = set()
    lines = text.splitlines()
    search_start = 0

    def visit(value: Any, parts: list[str]) -> None:
        nonlocal search_start
        if len(parts) > MAX_CATALOG_DEPTH:
            raise ValueError(f"catalog nesting exceeds {MAX_CATALOG_DEPTH} levels")
        if isinstance(value, str):
            if len(value) > MAX_MESSAGE_CHARACTERS:
                raise ValueError(
                    f"catalog value at /{'/'.join(parts)} exceeds "
                    f"{MAX_MESSAGE_CHARACTERS} characters"
                )
            if len(messages) >= MAX_CATALOG_MESSAGES:
                raise ValueError(f"catalog exceeds {MAX_CATALOG_MESSAGES} messages")
            pointer = "/" + "/".join(_pointer_part(part) for part in parts)
            if pointer in seen:
                raise ValueError(f"catalog path collision: {pointer}")
            seen.add(pointer)
            line, search_start = _line_for_key(lines, parts[-1], search_start)
            messages.append(CatalogMessage(pointer, value, line))
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if not parts and key.startswith("@"):  # ARB metadata and @@locale
                    continue
                visit(child, [*parts, key])
            return
        pointer = "/" + "/".join(_pointer_part(part) for part in parts)
        raise ValueError(
            f"catalog value at {pointer or '/'} must be a string or nested object, "
            f"not {type(value).__name__}"
        )

    for top_key, top_value in payload.items():
        if top_key.startswith("@"):
            continue
        visit(top_value, [top_key])
    if not messages:
        raise ValueError("locale catalog contains no translatable string values")
    return messages


_DANGEROUS_BIDI = {
    "\u202a": "LEFT-TO-RIGHT EMBEDDING",
    "\u202b": "RIGHT-TO-LEFT EMBEDDING",
    "\u202c": "POP DIRECTIONAL FORMATTING",
    "\u202d": "LEFT-TO-RIGHT OVERRIDE",
    "\u202e": "RIGHT-TO-LEFT OVERRIDE",
    "\u2066": "LEFT-TO-RIGHT ISOLATE",
    "\u2067": "RIGHT-TO-LEFT ISOLATE",
    "\u2068": "FIRST STRONG ISOLATE",
    "\u2069": "POP DIRECTIONAL ISOLATE",
}
_INVISIBLE_FORMAT = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}


def _unicode_findings(
    key: str,
    source: str,
    target: str,
    *,
    path: str,
    line: int,
) -> list[CatalogFinding]:
    findings: list[CatalogFinding] = []
    extra = Counter(target) - Counter(source)
    bidi = [
        f"U+{ord(char):04X} {_DANGEROUS_BIDI[char]}"
        for char in extra
        if char in _DANGEROUS_BIDI
    ]
    if bidi:
        findings.append(
            CatalogFinding(
                key=key,
                issue_type="unexpected_bidi_control",
                severity="error",
                explanation="Target adds directional control characters: " + ", ".join(bidi),
                path=path,
                line=line,
            )
        )
    invisible = [
        f"U+{ord(char):04X} {unicodedata.name(char, 'UNKNOWN')}"
        for char in extra
        if char in _INVISIBLE_FORMAT
    ]
    if invisible:
        findings.append(
            CatalogFinding(
                key=key,
                issue_type="unexpected_invisible_character",
                severity="warning",
                explanation="Target adds invisible format characters: " + ", ".join(invisible),
                path=path,
                line=line,
            )
        )
    surrogates = sorted(
        {f"U+{ord(char):04X}" for char in target if unicodedata.category(char) == "Cs"}
    )
    if surrogates:
        findings.append(
            CatalogFinding(
                key=key,
                issue_type="invalid_unicode_surrogate",
                severity="error",
                explanation="Target contains isolated Unicode surrogate code points: "
                + ", ".join(surrogates),
                path=path,
                line=line,
            )
        )
    return findings


def compare_locale_catalogs(
    source: list[CatalogMessage],
    target: list[CatalogMessage],
    *,
    source_path: Path,
    target_path: Path,
) -> list[CatalogFinding]:
    before = {item.key: item for item in source}
    after = {item.key: item for item in target}
    target_name = os.fspath(target_path)
    findings: list[CatalogFinding] = []

    for key in sorted(set(before) - set(after)):
        findings.append(
            CatalogFinding(
                key=key,
                issue_type="missing_translation_key",
                severity="error",
                explanation="The source key is missing from the target locale.",
                path=target_name,
                line=1,
            )
        )
    for key in sorted(set(after) - set(before)):
        findings.append(
            CatalogFinding(
                key=key,
                issue_type="orphan_translation_key",
                severity="warning",
                explanation="The target key does not exist in the source locale.",
                path=target_name,
                line=after[key].line,
            )
        )
    for key in sorted(set(before) & set(after)):
        source_message = before[key]
        target_message = after[key]
        issues = analyze_entries(
            [
                {
                    "source_key": key,
                    "source_text": source_message.text,
                    "target_text": target_message.text,
                }
            ]
        )
        findings.extend(
            CatalogFinding(
                key=key,
                issue_type=issue.issue_type,
                severity=issue.severity,
                explanation=issue.explanation,
                path=target_name,
                line=target_message.line,
            )
            for issue in issues
        )
        findings.extend(
            _unicode_findings(
                key,
                source_message.text,
                target_message.text,
                path=target_name,
                line=target_message.line,
            )
        )

    return findings


def findings_as_json(findings: list[CatalogFinding]) -> list[dict[str, Any]]:
    return [asdict(finding) for finding in findings]


def finding_fingerprint(finding: CatalogFinding) -> str:
    body = "\x1f".join(
        (
            Path(finding.path).name,
            finding.issue_type,
            finding.severity,
            finding.key,
            finding.explanation,
        )
    )
    return sha256(body.encode("utf-8")).hexdigest()


def baseline_payload(findings: list[CatalogFinding]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "fingerprints": sorted({finding_fingerprint(finding) for finding in findings}),
    }


def load_baseline(path: Path) -> set[str]:
    path = Path(path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("baseline must be an object with schema_version 1")
    fingerprints = payload.get("fingerprints")
    if not isinstance(fingerprints, list) or not all(
        isinstance(item, str) and len(item) == 64 for item in fingerprints
    ):
        raise ValueError("baseline fingerprints must be a list of SHA-256 strings")
    return set(fingerprints)


def findings_as_sarif(
    findings: list[CatalogFinding],
    *,
    tool_name: str,
    tool_version: str,
) -> dict[str, Any]:
    rule_ids = sorted({finding.issue_type for finding in findings})
    level_map = {"error": "error", "warning": "warning", "info": "note"}
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": tool_name,
                        "version": tool_version,
                        "rules": [
                            {
                                "id": rule_id,
                                "shortDescription": {"text": rule_id.replace("_", " ")},
                            }
                            for rule_id in rule_ids
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": finding.issue_type,
                        "level": level_map.get(finding.severity, "warning"),
                        "message": {"text": f"{finding.key}: {finding.explanation}"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": Path(finding.path).as_posix()},
                                    "region": {"startLine": max(1, finding.line)},
                                }
                            }
                        ],
                    }
                    for finding in findings
                ],
            }
        ],
    }


def write_json_atomic(payload: dict[str, Any], destination: Path) -> Path:
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination
