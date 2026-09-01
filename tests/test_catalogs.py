from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tercume_akis.catalogs import (
    baseline_payload,
    compare_locale_catalogs,
    finding_fingerprint,
    findings_as_sarif,
    load_baseline,
    load_json_catalog,
)
from tercume_akis.cli import main


class CatalogContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_json(self, name: str, payload: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_nested_json_and_arb_metadata_are_loaded_as_json_pointers(self) -> None:
        path = self._write_json(
            "en.arb",
            {
                "@@locale": "en",
                "title": "Home",
                "@title": {"description": "Page title"},
                "nav": {"save": "Save"},
            },
        )
        messages = {message.key: message.text for message in load_json_catalog(path)}
        self.assertEqual({"/title": "Home", "/nav/save": "Save"}, messages)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        path = self.root / "duplicate.json"
        path.write_text('{"save":"Save","save":"Store"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            load_json_catalog(path)

    def test_catalog_size_limit_is_enforced_before_parsing(self) -> None:
        path = self._write_json("large.json", {"message": "Hello"})
        with patch("tercume_akis.catalogs.MAX_CATALOG_BYTES", 5):
            with self.assertRaisesRegex(ValueError, "safety limit"):
                load_json_catalog(path)

    def test_contract_detects_key_placeholder_and_unicode_risks(self) -> None:
        source_path = self._write_json(
            "en.json",
            {
                "missing": "Delete",
                "count": "{count} files",
                "direction": "Account",
            },
        )
        target_path = self._write_json(
            "tr.json",
            {
                "count": "Dosyalar",
                "direction": "Hesap\u202e",
                "extra": "Fazla",
            },
        )
        findings = compare_locale_catalogs(
            load_json_catalog(source_path),
            load_json_catalog(target_path),
            source_path=source_path,
            target_path=target_path,
        )
        issue_types = {finding.issue_type for finding in findings}
        self.assertIn("missing_translation_key", issue_types)
        self.assertIn("orphan_translation_key", issue_types)
        self.assertIn("placeholder_mismatch", issue_types)
        self.assertIn("unexpected_bidi_control", issue_types)
        self.assertTrue(all(finding.line >= 1 for finding in findings))

    def test_sarif_and_cli_report_are_machine_readable(self) -> None:
        source_path = self._write_json("en.json", {"hello": "Hello, {name}"})
        target_path = self._write_json("tr.json", {"hello": "Merhaba"})
        findings = compare_locale_catalogs(
            load_json_catalog(source_path),
            load_json_catalog(target_path),
            source_path=source_path,
            target_path=target_path,
        )
        sarif = findings_as_sarif(findings, tool_name="test", tool_version="0")
        self.assertEqual("2.1.0", sarif["version"])
        self.assertEqual("placeholder_mismatch", sarif["runs"][0]["results"][0]["ruleId"])

        report = self.root / "report.sarif"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    "check-locales",
                    "--source",
                    str(source_path),
                    "--target",
                    str(target_path),
                    "--output-format",
                    "sarif",
                    "--report-file",
                    str(report),
                ]
            )
        self.assertEqual(1, exit_code)
        self.assertEqual("2.1.0", json.loads(report.read_text(encoding="utf-8"))["version"])
        self.assertIn('"ruleId": "placeholder_mismatch"', output.getvalue())

    def test_baseline_suppresses_only_matching_findings(self) -> None:
        source_path = self._write_json("en.json", {"hello": "Hello, {name}"})
        target_path = self._write_json("tr.json", {"hello": "Merhaba"})
        findings = compare_locale_catalogs(
            load_json_catalog(source_path),
            load_json_catalog(target_path),
            source_path=source_path,
            target_path=target_path,
        )
        baseline_path = self.root / "baseline.json"
        baseline_path.write_text(
            json.dumps(baseline_payload(findings)),
            encoding="utf-8",
        )
        fingerprints = load_baseline(baseline_path)
        self.assertIn(finding_fingerprint(findings[0]), fingerprints)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    "check-locales",
                    "--source",
                    str(source_path),
                    "--target",
                    str(target_path),
                    "--baseline",
                    str(baseline_path),
                ]
            )
        self.assertEqual(0, exit_code)
        self.assertIn("PASS", output.getvalue())

    def test_multiple_target_catalogs_are_checked_in_one_run(self) -> None:
        source_path = self._write_json("en.json", {"hello": "Hello, {name}"})
        valid_path = self._write_json("de.json", {"hello": "Hallo, {name}"})
        invalid_path = self._write_json("tr.json", {"hello": "Merhaba"})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    "check-locales",
                    "--source",
                    str(source_path),
                    "--target",
                    str(valid_path),
                    str(invalid_path),
                ]
            )
        self.assertEqual(1, exit_code)
        self.assertIn(str(valid_path), output.getvalue())
        self.assertIn("placeholder_mismatch", output.getvalue())


if __name__ == "__main__":
    unittest.main()
