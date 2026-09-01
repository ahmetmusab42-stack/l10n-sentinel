from __future__ import annotations

from pathlib import Path
from typing import Any

from ..backup import create_backup
from ..catalog import DEFAULT_SAMPLE_PROJECT, PRODUCT_SLUG
from ..formats import (
    document_from_current_project,
    dump_localization_document,
    load_localization_document,
)
from ..storage import ProjectRepository
from .base import WorkflowBase, WorkflowValidationError


class LocalizationWorkflow(WorkflowBase):
    product_id = PRODUCT_SLUG

    def __init__(self, repository: ProjectRepository) -> None:
        self.repository = repository

    def create_project(
        self,
        *,
        slug: str,
        name: str,
        source_language: str,
        target_language: str,
        description: str = "",
    ) -> str:
        return self.repository.create_project(
            slug=self.required(slug, "Project slug", maximum=80).lower(),
            name=self.required(name, "Project name", maximum=120),
            source_language=self.required(source_language, "Source language", maximum=16),
            target_language=self.required(target_language, "Target language", maximum=16),
            description=description.strip(),
        )

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
        source_key = self.required(source_key, "Source key", maximum=120)
        source_text = self.required(source_text, "Source text", maximum=5000)
        if translation_status not in {"draft", "translated", "review", "done"}:
            raise WorkflowValidationError("invalid translation status")
        if review_status not in {"pending", "in-review", "approved", "rejected"}:
            raise WorkflowValidationError("invalid review status")
        return self.repository.add_entry(
            project_slug=project_slug,
            source_key=source_key,
            source_text=source_text,
            target_text=target_text,
            translation_status=translation_status,
            review_status=review_status,
            context=context,
            notes=notes,
        )

    def set_translation(
        self,
        entry_id: str,
        target_text: str,
        *,
        review_status: str = "pending",
    ) -> None:
        if review_status not in {"pending", "in-review", "approved", "rejected"}:
            raise WorkflowValidationError("invalid review status")
        self.repository.update_entry(
            entry_id,
            target_text=self.required(target_text, "Target text", maximum=5000),
            translation_status="translated",
            review_status=review_status,
        )

    def set_review_status(self, entry_id: str, review_status: str) -> None:
        if review_status not in {"pending", "in-review", "approved", "rejected"}:
            raise WorkflowValidationError("invalid review status")
        translation_status = "done" if review_status == "approved" else None
        self.repository.update_entry(
            entry_id,
            review_status=review_status,
            translation_status=translation_status,
        )

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
        if status not in {"active", "deprecated"}:
            raise WorkflowValidationError("invalid glossary status")
        return self.repository.add_glossary_term(
            project_slug=project_slug,
            source_term=self.required(source_term, "Source term", maximum=200),
            target_term=self.required(target_term, "Target term", maximum=200),
            definition=definition.strip(),
            notes=notes.strip(),
            status=status,
        )

    def search_entries(self, project_slug: str, query: str) -> list[dict[str, Any]]:
        return self.repository.list_entries(project_slug, search=query)

    def search_glossary(self, project_slug: str, query: str) -> list[dict[str, Any]]:
        return self.repository.list_glossary_terms(project_slug, search=query)

    def export_project(
        self,
        project_slug: str,
        destination: Path,
        *,
        format_name: str | None = None,
    ) -> Path:
        bundle = self.repository.export_project_bundle(project_slug)
        document = document_from_current_project(
            bundle["project"],
            bundle["entries"],
            bundle.get("glossary"),
        )
        return dump_localization_document(document, destination, format_name)

    def import_project(
        self,
        source: Path,
        *,
        format_name: str | None = None,
        project_slug: str | None = None,
        replace: bool = False,
    ) -> str:
        source = self.validate_path(source, "Import file")
        document = load_localization_document(source, format_name)
        target_slug = project_slug or str(document.project.get("slug", "")).strip().lower()
        if not target_slug:
            raise WorkflowValidationError("project slug is required for import")
        project = dict(document.project)
        project.update(
            {
                "slug": target_slug,
                "name": project.get("name") or target_slug,
                "source_language": project.get("source_language") or "en",
                "target_language": project.get("target_language") or "tr",
                "description": project.get("description") or "",
            }
        )
        self.repository.create_project(
            slug=target_slug,
            name=str(project["name"]),
            source_language=str(project["source_language"]),
            target_language=str(project["target_language"]),
            description=str(project["description"]),
            overwrite=replace,
        )
        for item in document.entries:
            self.repository.upsert_entry(
                project_slug=target_slug,
                source_key=item.key,
                source_text=item.source_text,
                target_text=item.translation_text,
                translation_status=item.translation_status,
                review_status=item.review_status,
                context=item.context,
                notes=item.notes,
            )
        for term in document.glossary:
            self.repository.add_glossary_term(
                project_slug=target_slug,
                source_term=str(term.get("source_term", "")),
                target_term=str(term.get("target_term", "")),
                definition=str(term.get("definition", "")),
                notes=str(term.get("notes", "")),
                status=str(term.get("status", "active")),
            )
        return target_slug

    def create_sample_project(self) -> str:
        slug = self.create_project(
            slug=DEFAULT_SAMPLE_PROJECT.slug,
            name=DEFAULT_SAMPLE_PROJECT.name,
            source_language=DEFAULT_SAMPLE_PROJECT.source_language,
            target_language=DEFAULT_SAMPLE_PROJECT.target_language,
            description=DEFAULT_SAMPLE_PROJECT.description,
        )
        self.add_glossary_term(
            project_slug=slug,
            source_term="Terms of Service",
            target_term="Hizmet Koşulları",
            definition="Legal page header used in product settings.",
            notes="Synthetic sample data.",
        )
        entry = self.add_entry(
            project_slug=slug,
            source_key="nav.home",
            source_text="Home",
            target_text="Ana Sayfa",
            translation_status="translated",
            review_status="approved",
            context="Main navigation label.",
        )
        self.set_review_status(entry, "approved")
        self.add_entry(
            project_slug=slug,
            source_key="settings.language",
            source_text="Language",
            target_text="Dil",
            translation_status="translated",
            review_status="in-review",
            context="Settings page label.",
        )
        return slug

    def backup_project(self, project_slug: str, destination: Path) -> Path:
        return create_backup(self.repository, destination, project_slug=project_slug)
