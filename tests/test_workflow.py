from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tercume_akis.backup import create_backup, restore_database
from tercume_akis.catalog import DEFAULT_SAMPLE_PROJECT
from tercume_akis.storage import ProjectRepository
from tercume_akis.workflows import LocalizationWorkflow
from tercume_akis.workflows.base import WorkflowValidationError


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repository = ProjectRepository(self.root / "l10n-sentinel.sqlite3")
        self.workflow = LocalizationWorkflow(self.repository)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_project_creation_and_persistence(self) -> None:
        slug = self.workflow.create_project(
            slug="project-one",
            name="Project One",
            source_language="en",
            target_language="tr",
            description="Demo",
        )
        self.assertEqual("project-one", slug)
        self.assertEqual("Project One", self.repository.get_project(slug)["name"])

    def test_invalid_input_is_rejected(self) -> None:
        with self.assertRaises(WorkflowValidationError):
            self.workflow.create_project(
                slug="",
                name="X",
                source_language="en",
                target_language="tr",
            )
        slug = self.workflow.create_project(
            slug="project-two",
            name="Project Two",
            source_language="en",
            target_language="tr",
        )
        with self.assertRaises(WorkflowValidationError):
            self.workflow.add_entry(project_slug=slug, source_key="", source_text="Hello")

    def test_round_trip_export_import(self) -> None:
        slug = self.workflow.create_sample_project()
        export_path = self.root / "sample.json"
        self.workflow.export_project(slug, export_path)
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(slug, payload["project"]["slug"])
        imported = self.workflow.import_project(export_path, replace=True)
        self.assertEqual(slug, imported)
        self.assertGreaterEqual(len(self.repository.list_entries(slug)), 2)

    def test_backup_creates_zip(self) -> None:
        slug = self.workflow.create_sample_project()
        backup_path = self.root / "backup.zip"
        result = create_backup(self.repository, backup_path, project_slug=slug)
        self.assertTrue(result.is_file())
        restored_path = restore_database(backup_path, self.root / "restored.sqlite3")
        restored = ProjectRepository(restored_path)
        self.assertEqual(slug, restored.list_projects()[0]["slug"])

    def test_restore_rejects_unsafe_archive_member(self) -> None:
        archive_path = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("../escaped.sqlite3", b"not a database")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            restore_database(archive_path, self.root / "restored.sqlite3")

    def test_workflow_state_and_glossary(self) -> None:
        slug = self.workflow.create_project(
            slug="project-three",
            name="Project Three",
            source_language="en",
            target_language="tr",
        )
        entry = self.workflow.add_entry(
            project_slug=slug,
            source_key="hello",
            source_text="Hello",
        )
        self.workflow.set_translation(entry, "Merhaba")
        self.workflow.set_review_status(entry, "approved")
        terms = self.workflow.add_glossary_term(
            project_slug=slug,
            source_term="Save",
            target_term="Kaydet",
        )
        summary = self.repository.project_summary(slug)
        self.assertEqual(1, summary["approved_count"])
        self.assertTrue(terms)
        self.assertEqual("Kaydet", self.repository.list_glossary_terms(slug)[0]["target_term"])

    def test_search_and_sample_project(self) -> None:
        slug = self.workflow.create_sample_project()
        entries = self.workflow.search_entries(slug, "Home")
        self.assertGreaterEqual(len(entries), 1)
        self.assertEqual(DEFAULT_SAMPLE_PROJECT.slug, slug)


if __name__ == "__main__":
    unittest.main()
