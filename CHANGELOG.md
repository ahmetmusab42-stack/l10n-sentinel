# Changelog

All notable changes to this project are documented here.

## 0.3.1 — 2026-09-01

- Added credential-free PyPI publishing through GitHub OIDC.
- Isolated the PyPI identity token to a dedicated two-step publishing job.
- Updated GitHub Actions to their Node.js 24-compatible major releases.

## 0.3.0 — 2026-09-01

- Renamed the public distribution and CLI to L10n Sentinel.
- Added source-to-target JSON and ARB locale contract checks.
- Added deterministic multi-target checks for repositories with several locales.
- Added unambiguous JSON Pointer keys and duplicate-key rejection.
- Added missing/orphan key, Unicode bidi control, invisible character, and surrogate checks.
- Added explicit catalog size, depth, message-count, and value-length safety limits.
- Added SARIF, JSON, human, and GitHub annotation output for locale contracts.
- Added privacy-preserving finding baselines for gradual adoption in existing repositories.
- Expanded the composite GitHub Action with source/target mode and report output.
- Expanded the regression suite from 19 to 27 tests.

## 0.2.0 — Internal preview

- Repositioned the project around localization integrity for OSS maintainers.
- Added `validate` with human/JSON reports and CI-oriented exit codes.
- Added `diff` for added, removed, and changed source strings.
- Added markup mismatch and exact-source untranslated checks.
- Made localization exports atomic.
- Made SQLite backups consistent and restores path-safe and integrity-checked.
- Fixed PO round-trip handling for context, notes, and status metadata.
- Added fail-closed checks for unsupported PO and XLIFF constructs.
- Expanded the regression suite from 12 to 19 tests.

## 0.1.0 — Local prototype

- Created the independent Python package, local SQLite workspace, CLI, and Tkinter GUI.
- Added initial JSON project bundle, PO, and XLIFF 1.2 import/export support.
- Added initial localization QA and backup workflows.
