from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tercume_akis.formats import UnsafeFormatError, load_localization_document
from tercume_akis.integrity import compare_documents
from tercume_akis.models import LocalizationDocument, LocalizationEntry
from tercume_akis.qa import analyze_entries
from tercume_akis.storage import ProjectRepository
from tercume_akis.workflows import LocalizationWorkflow


class FormatAndQATests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _workflow(self, name: str) -> LocalizationWorkflow:
        repository = ProjectRepository(self.root / name / "l10n-sentinel.sqlite3")
        return LocalizationWorkflow(repository)

    def _make_project(self, workflow: LocalizationWorkflow) -> str:
        slug = workflow.create_project(
            slug="turkce-workbench",
            name="Türkçe Workbench",
            source_language="en",
            target_language="tr",
            description="Unicode round-trip project",
        )
        workflow.add_entry(
            project_slug=slug,
            source_key="greeting",
            source_text="Hello, {name}\nLine two",
            target_text="Merhaba, {name}\nİkinci satır",
            translation_status="translated",
            review_status="pending",
            context="Main greeting",
        )
        workflow.add_entry(
            project_slug=slug,
            source_key="farewell",
            source_text="Goodbye",
            target_text="Güle güle",
            translation_status="translated",
            review_status="approved",
        )
        return slug

    def _round_trip(self, format_name: str, suffix: str) -> None:
        source_workflow = self._workflow(f"source-{format_name}")
        slug = self._make_project(source_workflow)
        export_path = self.root / f"project{suffix}"
        source_workflow.export_project(slug, export_path, format_name=format_name)

        document = load_localization_document(export_path, format_name)
        self.assertEqual(slug, str(document.project.get("slug")))
        self.assertEqual("Türkçe Workbench", str(document.project.get("name")))

        import_workflow = self._workflow(f"dest-{format_name}")
        imported_slug = import_workflow.import_project(export_path, format_name=format_name)
        self.assertEqual(slug, imported_slug)
        entries = {
            item["source_key"]: item
            for item in import_workflow.repository.list_entries(slug)
        }
        self.assertEqual("Merhaba, {name}\nİkinci satır", entries["greeting"]["target_text"])
        self.assertEqual("Güle güle", entries["farewell"]["target_text"])
        self.assertEqual("Main greeting", entries["greeting"]["context"])
        self.assertEqual("pending", entries["greeting"]["review_status"])

    def test_json_round_trip_unicode(self) -> None:
        self._round_trip("json", ".json")

    def test_po_round_trip_unicode(self) -> None:
        self._round_trip("po", ".po")

    def test_xliff_round_trip_unicode(self) -> None:
        self._round_trip("xliff", ".xlf")

    def test_placeholder_duplicate_and_whitespace_qa(self) -> None:
        issues = analyze_entries(
            [
                {
                    "source_key": "dup-key",
                    "source_text": "Hello, {name} %s",
                    "target_text": "Merhaba, %s",
                },
                {
                    "source_key": "dup-key",
                    "source_text": "Hello, {name} %s",
                    "target_text": "Merhaba, {name} %s",
                },
                {
                    "source_key": "missing-placeholder",
                    "source_text": "Order %1 for {count} items",
                    "target_text": "Sipariş oluşturuldu",
                },
            ]
        )
        issue_types = {issue.issue_type for issue in issues}
        self.assertIn("placeholder_mismatch", issue_types)
        self.assertIn("duplicate_key", issue_types)

    def test_positional_printf_icu_and_mustache_placeholders(self) -> None:
        issues = analyze_entries(
            [
                {
                    "source_key": "formats",
                    "source_text": "%1$05.2f {0} {count, plural, one item} {{ user }}",
                    "target_text": "%1$05.2f {0} {{user}}",
                }
            ]
        )
        mismatch = next(issue for issue in issues if issue.issue_type == "placeholder_mismatch")
        self.assertIn("{count}", mismatch.explanation)
        self.assertNotIn("%1$05.2f", mismatch.explanation)

    def test_empty_untranslated_whitespace_and_newline_qa(self) -> None:
        issues = analyze_entries(
            [
                {"source_key": "empty", "source_text": "Hello", "target_text": ""},
                {"source_key": "whitespace", "source_text": "Title", "target_text": " Title "},
                {
                    "source_key": "newline",
                    "source_text": "Line one\nLine two",
                    "target_text": "Satır bir",
                },
            ]
        )
        issue_types = {issue.issue_type for issue in issues}
        self.assertIn("empty_translation", issue_types)
        self.assertIn("untranslated_entry", issue_types)
        self.assertIn("whitespace_difference", issue_types)
        self.assertIn("newline_mismatch", issue_types)

    def test_exact_source_match_and_markup_mismatch_qa(self) -> None:
        issues = analyze_entries(
            [
                {
                    "source_key": "same",
                    "source_text": "Open",
                    "target_text": "Open",
                },
                {
                    "source_key": "markup",
                    "source_text": "<b>Hello</b>",
                    "target_text": "<b>Merhaba",
                },
            ]
        )
        issue_types = {issue.issue_type for issue in issues}
        self.assertIn("untranslated_entry", issue_types)
        self.assertIn("markup_mismatch", issue_types)
        self.assertIn("unbalanced_markup", issue_types)

    def test_unsafe_po_plural_is_rejected(self) -> None:
        path = self.root / "plural.po"
        path.write_text(
            'msgid "item"\nmsgid_plural "items"\nmsgstr[0] "öğe"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(UnsafeFormatError, "plural"):
            load_localization_document(path, "po")

    def test_unsafe_xliff_inline_markup_is_rejected(self) -> None:
        path = self.root / "inline.xlf"
        path.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2">
  <file original="demo" source-language="en" target-language="tr" datatype="plaintext">
    <body><trans-unit id="hello"><source>Hello <ph id="1"/></source></trans-unit></body>
  </file>
</xliff>
""",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(UnsafeFormatError, "inline"):
            load_localization_document(path, "xliff")

    def test_source_change_comparison(self) -> None:
        baseline = LocalizationDocument(
            project={},
            entries=[
                LocalizationEntry("changed", "Save", "Kaydet"),
                LocalizationEntry("removed", "Delete", "Sil"),
            ],
        )
        current = LocalizationDocument(
            project={},
            entries=[
                LocalizationEntry("changed", "Save changes", "Kaydet"),
                LocalizationEntry("added", "Cancel", ""),
            ],
        )
        changes = compare_documents(baseline, current)
        change_types = {change.change_type for change in changes}
        self.assertEqual({"added", "removed", "source_changed"}, change_types)


if __name__ == "__main__":
    unittest.main()
