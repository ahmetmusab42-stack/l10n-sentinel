from __future__ import annotations

from textwrap import shorten


def render_projects(projects: list[dict[str, object]]) -> str:
    if not projects:
        return "No projects yet."
    lines = ["Projects:"]
    for item in projects:
        lines.append(
            "- "
            f"{item['slug']} | {item['name']} | "
            f"{item['source_language']} -> {item['target_language']}"
        )
    return "\n".join(lines)


def render_entries(entries: list[dict[str, object]]) -> str:
    if not entries:
        return "No translation entries."
    lines = ["Entries:"]
    for item in entries:
        source = shorten(str(item["source_text"]), width=42, placeholder="...")
        target = shorten(str(item["target_text"]), width=42, placeholder="...")
        lines.append(
            "- "
            f"{item['source_key']} | {item['translation_status']} / {item['review_status']} | "
            f"{source} => {target}"
        )
    return "\n".join(lines)


def render_glossary(terms: list[dict[str, object]]) -> str:
    if not terms:
        return "No glossary terms."
    lines = ["Glossary:"]
    for item in terms:
        lines.append(f"- {item['source_term']} => {item['target_term']} ({item['status']})")
    return "\n".join(lines)


def render_summary(summary: dict[str, object]) -> str:
    project = summary["project"]
    return (
        f"{project['name']} [{project['slug']}]\n"
        f"Languages: {project['source_language']} -> {project['target_language']}\n"
        f"Entries: {summary['entry_count']} | Glossary: {summary['glossary_count']} | "
        f"Draft: {summary['draft_count']} | Translated: {summary['translated_count']} | "
        f"In review: {summary['review_count']} | Approved: {summary['approved_count']}"
    )
