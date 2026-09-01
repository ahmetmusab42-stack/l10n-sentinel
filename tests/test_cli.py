from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tercume_akis.cli import main


class CliTests(unittest.TestCase):
    def test_sample_status_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            data_dir = root / "data"
            export_path = root / "project.json"
            backup_path = root / "project.zip"
            self.assertEqual(0, main(["--data-dir", str(data_dir), "sample"]))
            self.assertEqual(0, main(["--data-dir", str(data_dir), "status"]))
            self.assertEqual(
                0,
                main(
                    [
                        "--data-dir",
                        str(data_dir),
                        "export",
                        "--project",
                        "sample-project",
                        "--output",
                        str(export_path),
                    ]
                ),
            )
            self.assertTrue(export_path.is_file())
            self.assertEqual(
                0,
                main(
                    [
                        "--data-dir",
                        str(data_dir),
                        "backup",
                        "--project",
                        "sample-project",
                        "--output",
                        str(backup_path),
                    ]
                ),
            )
            self.assertTrue(backup_path.is_file())

    def test_validate_and_diff_are_ci_friendly(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            baseline_path = root / "baseline.json"
            current_path = root / "current.json"
            baseline = {
                "project": {"slug": "demo"},
                "entries": [
                    {
                        "source_key": "greeting",
                        "source_text": "Hello {name}",
                        "target_text": "Merhaba {name}",
                    }
                ],
            }
            current = {
                "project": {"slug": "demo"},
                "entries": [
                    {
                        "source_key": "greeting",
                        "source_text": "Welcome {name}",
                        "target_text": "Merhaba",
                    }
                ],
            }
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            current_path.write_text(json.dumps(current), encoding="utf-8")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                validate_exit = main(
                    [
                        "validate",
                        "--input",
                        str(current_path),
                        "--output-format",
                        "json",
                    ]
                )
            self.assertEqual(1, validate_exit)
            self.assertIn("placeholder_mismatch", output.getvalue())

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                diff_exit = main(
                    [
                        "diff",
                        "--baseline",
                        str(baseline_path),
                        "--current",
                        str(current_path),
                        "--output-format",
                        "json",
                    ]
                )
            self.assertEqual(1, diff_exit)
            self.assertIn("source_changed", output.getvalue())

    def test_validate_reports_malformed_input_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "bad.json"
            path.write_text("{not-json", encoding="utf-8")
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                exit_code = main(["validate", "--input", str(path)])
            self.assertEqual(2, exit_code)
            self.assertIn("error:", error.getvalue())


if __name__ == "__main__":
    unittest.main()
