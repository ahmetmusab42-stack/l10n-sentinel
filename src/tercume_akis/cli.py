from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .catalog import DEFAULT_SAMPLE_PROJECT, PRODUCT_NAME, PRODUCT_SLUG
from .catalogs import (
    CatalogFinding,
    baseline_payload,
    compare_locale_catalogs,
    finding_fingerprint,
    findings_as_json,
    findings_as_sarif,
    load_baseline,
    load_json_catalog,
    write_json_atomic,
)
from .formats import FORMAT_NAMES, load_localization_document, normalize_format_name
from .gui import launch_gui
from .integrity import compare_documents, count_by_severity, validate_document
from .paths import default_data_root
from .storage import ProjectRepository
from .ui import render_entries, render_glossary, render_projects, render_summary
from .workflows import LocalizationWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PRODUCT_SLUG,
        description=f"{PRODUCT_NAME} localization workflow",
    )
    parser.add_argument("--data-dir", help="Override the local data directory")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show local workspace status")
    sub.add_parser("list-projects", help="List projects")

    sample = sub.add_parser("sample", help="Create or refresh the sample project")
    sample.add_argument("--replace", action="store_true")

    new_project = sub.add_parser("new-project", help="Create a project")
    new_project.add_argument("--slug", required=True)
    new_project.add_argument("--name", required=True)
    new_project.add_argument("--source-language", required=True)
    new_project.add_argument("--target-language", required=True)
    new_project.add_argument("--description", default="")

    add_entry = sub.add_parser("add-entry", help="Add a translation entry")
    add_entry.add_argument("--project", required=True)
    add_entry.add_argument("--key", required=True)
    add_entry.add_argument("--source", required=True)
    add_entry.add_argument("--target", default="")
    add_entry.add_argument("--translation-status", default="draft")
    add_entry.add_argument("--review-status", default="pending")
    add_entry.add_argument("--context", default="")
    add_entry.add_argument("--notes", default="")

    set_translation = sub.add_parser("set-translation", help="Set an entry translation")
    set_translation.add_argument("--entry-id", required=True)
    set_translation.add_argument("--target", required=True)
    set_translation.add_argument("--review-status", default="pending")

    review = sub.add_parser("set-review", help="Set review status")
    review.add_argument("--entry-id", required=True)
    review.add_argument("--status", required=True)

    glossary = sub.add_parser("add-glossary", help="Add a glossary term")
    glossary.add_argument("--project", required=True)
    glossary.add_argument("--source", required=True)
    glossary.add_argument("--target", required=True)
    glossary.add_argument("--definition", default="")
    glossary.add_argument("--notes", default="")
    glossary.add_argument("--status", default="active")

    export = sub.add_parser("export", help="Export a project to JSON")
    export.add_argument("--project", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--format", choices=FORMAT_NAMES, default=None)

    imp = sub.add_parser("import", help="Import a project from JSON")
    imp.add_argument("--input", required=True)
    imp.add_argument("--project")
    imp.add_argument("--format", choices=FORMAT_NAMES, default=None)
    imp.add_argument("--replace", action="store_true")

    backup = sub.add_parser("backup", help="Create a zipped backup")
    backup.add_argument("--project", required=False)
    backup.add_argument("--output", required=True)

    search = sub.add_parser("search", help="Search entries and glossary")
    search.add_argument("--project", required=True)
    search.add_argument("--query", required=True)

    validate = sub.add_parser("validate", help="Validate a localization file for CI")
    validate.add_argument("--input", required=True)
    validate.add_argument("--format", choices=FORMAT_NAMES, default=None)
    validate.add_argument("--output-format", choices=("human", "json"), default="human")
    validate.add_argument(
        "--fail-on",
        choices=("never", "warning", "error"),
        default="error",
        help="Lowest severity that returns exit code 1",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    diff = sub.add_parser("diff", help="Compare two localization file revisions")
    diff.add_argument("--baseline", required=True)
    diff.add_argument("--current", required=True)
    diff.add_argument("--baseline-format", choices=FORMAT_NAMES, default=None)
    diff.add_argument("--current-format", choices=FORMAT_NAMES, default=None)
    diff.add_argument("--output-format", choices=("human", "json"), default="human")
    diff.add_argument(
        "--fail-on",
        choices=("never", "warning", "error"),
        default="error",
        help="Lowest severity that returns exit code 1",
    )

    locale_check = sub.add_parser(
        "check-locales",
        help="Check a JSON or ARB target locale against its source locale",
    )
    locale_check.add_argument("--source", required=True)
    locale_check.add_argument(
        "--target",
        required=True,
        nargs="+",
        help="One or more target JSON or ARB locale catalogs",
    )
    locale_check.add_argument(
        "--output-format",
        choices=("human", "json", "sarif", "github"),
        default="human",
    )
    locale_check.add_argument("--report-file", help="Write JSON or SARIF output atomically")
    baseline_group = locale_check.add_mutually_exclusive_group()
    baseline_group.add_argument("--baseline", help="Suppress findings recorded in a baseline file")
    baseline_group.add_argument(
        "--write-baseline",
        help="Write current finding fingerprints and return exit code 0",
    )
    locale_check.add_argument(
        "--fail-on",
        choices=("never", "warning", "error"),
        default="error",
        help="Lowest severity that returns exit code 1",
    )

    sub.add_parser("check", help="Run database integrity checks")
    sub.add_parser("gui", help="Launch the desktop GUI")
    return parser


def _repository(data_dir: str | None) -> ProjectRepository:
    if data_dir:
        root = Path(data_dir).expanduser().resolve()
    else:
        root = default_data_root()
    root.mkdir(parents=True, exist_ok=True)
    return ProjectRepository(root / f"{PRODUCT_SLUG}.sqlite3")


def _exit_for_severities(severities: list[str], fail_on: str) -> int:
    if fail_on == "never":
        return 0
    ranks = {"info": 0, "warning": 1, "error": 2}
    threshold = ranks[fail_on]
    return int(any(ranks.get(severity, 2) >= threshold for severity in severities))


def _print_findings(
    *,
    title: str,
    findings: list[object],
    output_format: str,
) -> None:
    serialized = [asdict(item) for item in findings]
    if output_format == "json":
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "tool": {"name": PRODUCT_NAME, "version": __version__},
                    "title": title,
                    "summary": count_by_severity(serialized),
                    "findings": serialized,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(title)
    if not serialized:
        print("PASS: no findings")
        return
    for finding in serialized:
        finding_type = finding.get("issue_type") or finding.get("change_type")
        print(
            f"{str(finding['severity']).upper():7} "
            f"{finding['key']} [{finding_type}] {finding['explanation']}"
        )
    summary = count_by_severity(serialized)
    print("Summary: " + ", ".join(f"{key}={value}" for key, value in summary.items()))


def _github_escape(value: str, *, property_value: bool = False) -> str:
    result = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if property_value:
        result = result.replace(":", "%3A").replace(",", "%2C")
    return result


def _print_catalog_findings(
    findings: list[CatalogFinding],
    *,
    source: Path,
    targets: list[Path],
    output_format: str,
    report_file: str | None,
) -> None:
    serialized = findings_as_json(findings)
    summary = count_by_severity(serialized)
    title = f"Locale contract: {source} -> {', '.join(str(path) for path in targets)}"
    if output_format == "sarif":
        payload = findings_as_sarif(
            findings,
            tool_name=PRODUCT_NAME,
            tool_version=__version__,
        )
    else:
        payload = {
            "schema_version": 1,
            "tool": {"name": PRODUCT_NAME, "version": __version__},
            "title": title,
            "summary": summary,
            "findings": serialized,
        }

    if report_file:
        write_json_atomic(payload, Path(report_file))

    if output_format in {"json", "sarif"}:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if output_format == "github":
        for finding in findings:
            command = "error" if finding.severity == "error" else "warning"
            path = _github_escape(finding.path, property_value=True)
            message = _github_escape(
                f"{finding.key} [{finding.issue_type}] {finding.explanation}"
            )
            print(f"::{command} file={path},line={max(1, finding.line)}::{message}")
        print("Locale integrity summary: " + ", ".join(
            f"{key}={value}" for key, value in summary.items()
        ))
        return

    print(title)
    if not findings:
        print("PASS: no findings")
        return
    for finding in findings:
        print(
            f"{finding.severity.upper():7} {finding.path}:{finding.line} "
            f"{finding.key} [{finding.issue_type}] {finding.explanation}"
        )
    print("Summary: " + ", ".join(f"{key}={value}" for key, value in summary.items()))


def _run_file_command(args: argparse.Namespace) -> int | None:
    if args.command == "validate":
        document = load_localization_document(Path(args.input), args.format)
        findings = validate_document(document)
        _print_findings(
            title=f"Validation: {Path(args.input)}",
            findings=findings,
            output_format=args.output_format,
        )
        return _exit_for_severities([item.severity for item in findings], args.fail_on)
    if args.command == "diff":
        baseline = load_localization_document(Path(args.baseline), args.baseline_format)
        current = load_localization_document(Path(args.current), args.current_format)
        findings = compare_documents(baseline, current)
        _print_findings(
            title=f"Localization diff: {Path(args.baseline)} -> {Path(args.current)}",
            findings=findings,
            output_format=args.output_format,
        )
        return _exit_for_severities([item.severity for item in findings], args.fail_on)
    if args.command == "check-locales":
        source_path = Path(args.source)
        target_paths = [Path(value) for value in args.target]
        source = load_json_catalog(source_path)
        findings: list[CatalogFinding] = []
        for target_path in target_paths:
            findings.extend(
                compare_locale_catalogs(
                    source,
                    load_json_catalog(target_path),
                    source_path=source_path,
                    target_path=target_path,
                )
            )
        if args.write_baseline:
            destination = write_json_atomic(
                baseline_payload(findings),
                Path(args.write_baseline),
            )
            print(f"Baseline written: {destination} ({len(findings)} findings)")
            return 0
        if args.baseline:
            fingerprints = load_baseline(Path(args.baseline))
            findings = [
                finding
                for finding in findings
                if finding_fingerprint(finding) not in fingerprints
            ]
        _print_catalog_findings(
            findings,
            source=source_path,
            targets=target_paths,
            output_format=args.output_format,
            report_file=args.report_file,
        )
        return _exit_for_severities([item.severity for item in findings], args.fail_on)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        file_result = _run_file_command(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if file_result is not None:
        return file_result
    repository = _repository(args.data_dir)
    workflow = LocalizationWorkflow(repository)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "status":
        projects = repository.list_projects()
        if not projects:
            print("No projects yet.")
            return 0
        first_slug = projects[0]["slug"]
        print(render_summary(repository.project_summary(first_slug)))
        return 0

    if args.command == "list-projects":
        print(render_projects(repository.list_projects()))
        return 0

    if args.command == "sample":
        slug = (
            workflow.create_sample_project()
            if args.replace
            or not any(p["slug"] == DEFAULT_SAMPLE_PROJECT.slug for p in repository.list_projects())
            else DEFAULT_SAMPLE_PROJECT.slug
        )
        print(f"Sample project ready: {slug}")
        return 0

    if args.command == "new-project":
        slug = workflow.create_project(
            slug=args.slug,
            name=args.name,
            source_language=args.source_language,
            target_language=args.target_language,
            description=args.description,
        )
        print(f"Project created: {slug}")
        return 0

    if args.command == "add-entry":
        entry_id = workflow.add_entry(
            project_slug=args.project,
            source_key=args.key,
            source_text=args.source,
            target_text=args.target,
            translation_status=args.translation_status,
            review_status=args.review_status,
            context=args.context,
            notes=args.notes,
        )
        print(f"Entry added: {entry_id}")
        return 0

    if args.command == "set-translation":
        workflow.set_translation(args.entry_id, args.target, review_status=args.review_status)
        print("Translation updated")
        return 0

    if args.command == "set-review":
        workflow.set_review_status(args.entry_id, args.status)
        print("Review updated")
        return 0

    if args.command == "add-glossary":
        term_id = workflow.add_glossary_term(
            project_slug=args.project,
            source_term=args.source,
            target_term=args.target,
            definition=args.definition,
            notes=args.notes,
            status=args.status,
        )
        print(f"Glossary term added: {term_id}")
        return 0

    if args.command == "export":
        output_path = Path(args.output)
        selected_format = (
            normalize_format_name(args.format, output_path) if args.format else None
        )
        destination = workflow.export_project(
            args.project,
            output_path,
            format_name=selected_format,
        )
        print(destination)
        return 0

    if args.command == "import":
        input_path = Path(args.input)
        selected_format = (
            normalize_format_name(args.format, input_path) if args.format else None
        )
        slug = workflow.import_project(
            input_path,
            format_name=selected_format,
            project_slug=args.project,
            replace=args.replace,
        )
        print(f"Imported: {slug}")
        return 0

    if args.command == "backup":
        destination = workflow.backup_project(
            args.project or DEFAULT_SAMPLE_PROJECT.slug,
            Path(args.output),
        )
        print(destination)
        return 0

    if args.command == "search":
        entries = workflow.search_entries(args.project, args.query)
        terms = workflow.search_glossary(args.project, args.query)
        print(render_entries(entries))
        print(render_glossary(terms))
        return 0

    if args.command == "check":
        repository.integrity_check()
        print("Integrity check passed")
        return 0

    if args.command == "gui":
        launch_gui()
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
