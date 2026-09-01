from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import LocalizationDocument, LocalizationEntry

FORMAT_NAMES = ("json", "po", "xliff")


class UnsafeFormatError(ValueError):
    """Raised when importing a file would silently discard unsupported data."""


def normalize_format_name(format_name: str | None, path: Path | None = None) -> str:
    if format_name:
        name = format_name.strip().lower()
        if name in {"xlf", "xliff1.2", "xliff12"}:
            return "xliff"
        if name not in FORMAT_NAMES:
            raise ValueError(f"unsupported localization format: {format_name}")
        return name
    if path is None:
        return "json"
    suffix = path.suffix.lower()
    if suffix == ".po":
        return "po"
    if suffix in {".xlf", ".xliff", ".xml"}:
        return "xliff"
    return "json"


def document_from_project_bundle(bundle: Mapping[str, object]) -> LocalizationDocument:
    return LocalizationDocument.from_bundle(dict(bundle))


def document_from_entries(
    project: Mapping[str, object],
    entries: Iterable[Mapping[str, object]],
    glossary: Iterable[Mapping[str, object]] | None = None,
) -> LocalizationDocument:
    return LocalizationDocument(
        project=dict(project),
        entries=[
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
            for item in entries
        ],
        glossary=[dict(item) for item in (glossary or [])],
    )


def _json_dumps(document: LocalizationDocument) -> str:
    return json.dumps(document.to_bundle(), ensure_ascii=False, indent=2)


_PO_ESCAPE_MAP = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _po_escape(text: str) -> str:
    return ''.join(_PO_ESCAPE_MAP.get(char, char) for char in text)


def _po_unescape(text: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "\\" or index + 1 >= len(text):
            result.append(char)
            index += 1
            continue
        next_char = text[index + 1]
        mapping = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
        if next_char not in mapping:
            raise UnsafeFormatError(f"unsupported PO escape sequence: \\{next_char}")
        result.append(mapping[next_char])
        index += 2
    return "".join(result)


def _po_quote(text: str) -> str:
    return f'"{_po_escape(text)}"'


def _po_join_lines(*parts: str) -> str:
    return "\n".join(parts)


def _parse_po_quoted(line: str) -> str:
    line = line.strip()
    if not (line.startswith('"') and line.endswith('"')):
        raise ValueError("invalid PO string literal")
    return _po_unescape(line[1:-1])


def _po_project_headers(project: Mapping[str, object]) -> list[str]:
    return [
        f"# L10n-Sentinel-Project-Slug: {project.get('slug', '')}",
        f"# L10n-Sentinel-Project-Name: {project.get('name', '')}",
        f"# L10n-Sentinel-Source-Language: {project.get('source_language', '')}",
        f"# L10n-Sentinel-Target-Language: {project.get('target_language', '')}",
        f"# L10n-Sentinel-Project-Description: {project.get('description', '')}",
    ]


def _po_dump(document: LocalizationDocument) -> str:
    lines = [*_po_project_headers(document.project), ""]
    for entry in document.entries:
        if entry.context:
            lines.append(f"#. context: {_po_escape(entry.context)}")
        if entry.notes:
            lines.append(f"#. notes: {_po_escape(entry.notes)}")
        lines.append(f"#. status: {_po_escape(entry.translation_status)}")
        lines.append(f"#. review: {_po_escape(entry.review_status)}")
        lines.append(f"msgctxt {_po_quote(entry.key)}")
        lines.append(f"msgid {_po_quote(entry.source_text)}")
        lines.append(f"msgstr {_po_quote(entry.translation_text)}")
        lines.append("")
    return _po_join_lines(*lines).rstrip() + "\n"


def _po_load(text: str) -> LocalizationDocument:
    project: dict[str, object] = {}
    entries: list[LocalizationEntry] = []
    current: dict[str, str] | None = None
    current_field: str | None = None
    pending_metadata: dict[str, str] = {}

    def ensure_current() -> dict[str, str]:
        nonlocal current
        if current is None:
            current = dict(pending_metadata)
            pending_metadata.clear()
        return current

    def finish_current() -> None:
        nonlocal current
        if not current:
            return
        key = current.get("msgctxt") or current.get("msgid")
        source = current.get("msgid", "")
        translation = current.get("msgstr", "")
        is_header = current.get("msgid") == "" and not current.get("msgctxt")
        if is_header and translation:
            raise UnsafeFormatError(
                "PO header metadata is not preserved yet; refusing an unsafe import."
            )
        if not is_header and (key or source or translation):
            entries.append(
                LocalizationEntry(
                    key=key or source,
                    source_text=source,
                    translation_text=translation,
                    translation_status=current.get("status", "draft"),
                    review_status=current.get("review", "pending"),
                    context=current.get("context", ""),
                    notes=current.get("notes", ""),
                )
            )
        current = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            finish_current()
            pending_metadata.clear()
            current_field = None
            continue
        if stripped.startswith("# L10n-Sentinel-"):
            parts = stripped[1:].split(":", 1)
            if len(parts) == 2:
                label = parts[0].strip()
                value = parts[1].strip()
                if label == "L10n-Sentinel-Project-Slug":
                    project["slug"] = value
                elif label == "L10n-Sentinel-Project-Name":
                    project["name"] = value
                elif label == "L10n-Sentinel-Source-Language":
                    project["source_language"] = value
                elif label == "L10n-Sentinel-Target-Language":
                    project["target_language"] = value
                elif label == "L10n-Sentinel-Project-Description":
                    project["description"] = value
            continue
        if stripped.startswith("#."):
            payload = stripped[2:].strip()
            if payload.startswith("context:"):
                pending_metadata["context"] = payload.split(":", 1)[1].strip()
            elif payload.startswith("notes:"):
                pending_metadata["notes"] = payload.split(":", 1)[1].strip()
            elif payload.startswith("status:"):
                pending_metadata["status"] = payload.split(":", 1)[1].strip()
            elif payload.startswith("review:"):
                pending_metadata["review"] = payload.split(":", 1)[1].strip()
            else:
                raise UnsafeFormatError(
                    "PO extracted comments are not preserved yet; refusing an unsafe import."
                )
            continue
        if stripped.startswith("#"):
            raise UnsafeFormatError(
                "PO comments, references, flags, and obsolete entries are not preserved yet; "
                "refusing an unsafe import."
            )
        if stripped.startswith("msgid_plural") or stripped.startswith("msgstr["):
            raise UnsafeFormatError(
                "PO plural entries are not supported yet; refusing an unsafe import."
            )
        if stripped.startswith("msgctxt "):
            ensure_current()["msgctxt"] = _parse_po_quoted(stripped[len("msgctxt ") :])
            current_field = "msgctxt"
            continue
        if stripped.startswith("msgid "):
            ensure_current()["msgid"] = _parse_po_quoted(stripped[len("msgid ") :])
            current_field = "msgid"
            continue
        if stripped.startswith("msgstr "):
            ensure_current()["msgstr"] = _parse_po_quoted(stripped[len("msgstr ") :])
            current_field = "msgstr"
            continue
        if stripped.startswith('"') and current is not None and current_field is not None:
            current[current_field] = current.get(current_field, "") + _parse_po_quoted(stripped)
            continue
        raise ValueError(f"unsupported PO syntax: {stripped[:80]}")

    finish_current()
    if not project:
        project = {
            "slug": "",
            "name": "",
            "source_language": "",
            "target_language": "",
            "description": "",
        }
    return LocalizationDocument(project=project, entries=entries)


def _xliff_namespace() -> str:
    return "urn:oasis:names:tc:xliff:document:1.2"


def _xliff_qname(tag: str) -> str:
    return f"{{{_xliff_namespace()}}}{tag}"


def _xliff_dump(document: LocalizationDocument) -> str:
    ET.register_namespace("", _xliff_namespace())
    project = document.project
    root = ET.Element(_xliff_qname("xliff"), version="1.2")
    file_element = ET.SubElement(
        root,
        _xliff_qname("file"),
        attrib={
            "original": str(project.get("slug", "")),
            "source-language": str(project.get("source_language", "")),
            "target-language": str(project.get("target_language", "")),
            "datatype": "plaintext",
        },
    )
    header = ET.SubElement(file_element, _xliff_qname("header"))
    tool = ET.SubElement(header, _xliff_qname("tool"))
    tool.attrib.update({"tool-id": "l10n-sentinel", "tool-name": "L10n Sentinel"})
    if project.get("name"):
        note = ET.SubElement(header, _xliff_qname("note"), attrib={"from": "project-name"})
        note.text = str(project.get("name", ""))
    if project.get("description"):
        note = ET.SubElement(header, _xliff_qname("note"), attrib={"from": "project-description"})
        note.text = str(project.get("description", ""))
    body = ET.SubElement(file_element, _xliff_qname("body"))
    for entry in document.entries:
        trans_unit = ET.SubElement(
            body,
            _xliff_qname("trans-unit"),
            attrib={"id": entry.key, "resname": entry.key},
        )
        source = ET.SubElement(trans_unit, _xliff_qname("source"))
        source.attrib["{http://www.w3.org/XML/1998/namespace}space"] = "preserve"
        source.text = entry.source_text
        target = ET.SubElement(
            trans_unit,
            _xliff_qname("target"),
            attrib={"state": "translated" if entry.translation_text else "new"},
        )
        target.attrib["{http://www.w3.org/XML/1998/namespace}space"] = "preserve"
        target.text = entry.translation_text
        if entry.context:
            note = ET.SubElement(trans_unit, _xliff_qname("note"), attrib={"from": "context"})
            note.text = entry.context
        if entry.notes:
            note = ET.SubElement(trans_unit, _xliff_qname("note"), attrib={"from": "notes"})
            note.text = entry.notes
        note = ET.SubElement(trans_unit, _xliff_qname("note"), attrib={"from": "status"})
        note.text = entry.translation_status
        note = ET.SubElement(trans_unit, _xliff_qname("note"), attrib={"from": "review"})
        note.text = entry.review_status
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _strip_namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _xliff_load(text: str) -> LocalizationDocument:
    tree = ET.fromstring(text)
    if _strip_namespace(tree.tag) != "xliff" or tree.attrib.get("version") != "1.2":
        raise UnsafeFormatError("only XLIFF 1.2 documents are supported")
    if not tree.tag.startswith(f"{{{_xliff_namespace()}}}"):
        raise UnsafeFormatError("XLIFF 1.2 namespace is missing or unsupported")
    if set(tree.attrib) != {"version"}:
        raise UnsafeFormatError("unsupported XLIFF root metadata would be lost")
    if any(_strip_namespace(child.tag) != "file" for child in tree):
        raise UnsafeFormatError("unsupported XLIFF root content would be lost")
    files = tree.findall(_xliff_qname("file"))
    if len(files) != 1:
        raise UnsafeFormatError("exactly one XLIFF <file> element is required")
    file_element = files[0]
    allowed_file_attributes = {"original", "source-language", "target-language", "datatype"}
    if set(file_element.attrib) - allowed_file_attributes:
        raise UnsafeFormatError("unsupported XLIFF <file> metadata would be lost")
    project: dict[str, object] = {}
    entries: list[LocalizationEntry] = []
    project = {
        "slug": file_element.attrib.get("original", ""),
        "source_language": file_element.attrib.get("source-language", ""),
        "target_language": file_element.attrib.get("target-language", ""),
        "name": file_element.attrib.get("original", ""),
        "description": "",
    }
    allowed_file_children = {"header", "body"}
    if any(_strip_namespace(child.tag) not in allowed_file_children for child in file_element):
        raise UnsafeFormatError("unsupported XLIFF <file> content would be lost")
    header = file_element.find(_xliff_qname("header"))
    if header is not None:
        for child in header:
            child_name = _strip_namespace(child.tag)
            if child_name == "tool":
                if child.attrib != {
                    "tool-id": "l10n-sentinel",
                    "tool-name": "L10n Sentinel",
                }:
                    raise UnsafeFormatError("external XLIFF tool metadata would be lost")
                continue
            if child_name != "note" or child.attrib.get("from") not in {
                "project-name",
                "project-description",
            }:
                raise UnsafeFormatError("unsupported XLIFF header metadata would be lost")
            if child.attrib.get("from") == "project-name":
                project["name"] = child.text or ""
            else:
                project["description"] = child.text or ""
    body = file_element.find(_xliff_qname("body"))
    if body is None:
        raise ValueError("XLIFF document is missing a <body> element")
    if any(_strip_namespace(child.tag) != "trans-unit" for child in body):
        raise UnsafeFormatError("nested XLIFF groups are not supported yet")
    for unit in body.findall(_xliff_qname("trans-unit")):
        if set(unit.attrib) - {"id", "resname"}:
            raise UnsafeFormatError("unsupported XLIFF trans-unit metadata would be lost")
        sources = unit.findall(_xliff_qname("source"))
        targets = unit.findall(_xliff_qname("target"))
        if len(sources) != 1 or len(targets) > 1:
            raise UnsafeFormatError("unsupported XLIFF source/target structure")
        source_element = sources[0]
        target_element = targets[0] if targets else None
        if list(source_element) or (target_element is not None and list(target_element)):
            raise UnsafeFormatError(
                "XLIFF inline elements are not preserved yet; refusing an unsafe import."
            )
        allowed_space = {"{http://www.w3.org/XML/1998/namespace}space"}
        if set(source_element.attrib) - allowed_space:
            raise UnsafeFormatError("unsupported XLIFF source metadata would be lost")
        if target_element is not None and set(target_element.attrib) - (allowed_space | {"state"}):
            raise UnsafeFormatError("unsupported XLIFF target metadata would be lost")
        allowed_unit_children = {"source", "target", "note"}
        if any(_strip_namespace(child.tag) not in allowed_unit_children for child in unit):
            raise UnsafeFormatError("unsupported XLIFF trans-unit content would be lost")
        notes: dict[str, str] = {}
        for note in unit.findall(_xliff_qname("note")):
            note_from = note.attrib.get("from", "")
            if note_from not in {"context", "notes", "status", "review"}:
                raise UnsafeFormatError("unsupported XLIFF notes would be lost")
            notes[note_from] = note.text or ""
        key = unit.attrib.get("id") or unit.attrib.get("resname") or ""
        target = (target_element.text or "") if target_element is not None else ""
        entries.append(
            LocalizationEntry(
                key=key,
                source_text=source_element.text or "",
                translation_text=target,
                translation_status=notes.get("status", "translated" if target else "draft"),
                review_status=notes.get("review", "pending"),
                context=notes.get("context", ""),
                notes=notes.get("notes", ""),
            )
        )
    return LocalizationDocument(project=project, entries=entries)


class LocalizationFormat:
    name = "json"
    extensions: tuple[str, ...] = (".json",)

    def load_text(self, text: str) -> LocalizationDocument:
        return LocalizationDocument.from_bundle(json.loads(text))

    def dump_text(self, document: LocalizationDocument) -> str:
        return _json_dumps(document)


class PoLocalizationFormat:
    name = "po"
    extensions: tuple[str, ...] = (".po",)

    def load_text(self, text: str) -> LocalizationDocument:
        return _po_load(text)

    def dump_text(self, document: LocalizationDocument) -> str:
        return _po_dump(document)


class Xliff12LocalizationFormat:
    name = "xliff"
    extensions: tuple[str, ...] = (".xlf", ".xliff", ".xml")

    def load_text(self, text: str) -> LocalizationDocument:
        return _xliff_load(text)

    def dump_text(self, document: LocalizationDocument) -> str:
        return _xliff_dump(document)


FORMAT_REGISTRY = {
    "json": LocalizationFormat(),
    "po": PoLocalizationFormat(),
    "xliff": Xliff12LocalizationFormat(),
}


def load_localization_document(path: Path, format_name: str | None = None) -> LocalizationDocument:
    path = Path(path).expanduser().resolve()
    format_key = normalize_format_name(format_name, path)
    return FORMAT_REGISTRY[format_key].load_text(path.read_text(encoding="utf-8"))


def dump_localization_document(
    document: LocalizationDocument,
    path: Path,
    format_name: str | None = None,
) -> Path:
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    format_key = normalize_format_name(format_name, path)
    payload = FORMAT_REGISTRY[format_key].dump_text(document)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return path


def document_from_current_project(
    project: Mapping[str, object],
    entries: Iterable[Mapping[str, object]],
    glossary: Iterable[Mapping[str, object]] | None = None,
) -> LocalizationDocument:
    return document_from_entries(project, entries, glossary=glossary)
