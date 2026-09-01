# L10n Sentinel

L10n Sentinel is an offline localization contract checker for pull requests and release pipelines.
It catches changes that can leave a locale file syntactically valid but break an application at
runtime: missing keys, placeholder drift, markup damage, stale source strings, and unexpected
Unicode control characters.

It has no account, API key, hosted service, telemetry, or network requirement.

## Why this tool

General translation platforms are useful for authoring and collaboration. L10n Sentinel has a
smaller job: give maintainers a deterministic, reviewable answer to “is this localization change
safe to merge?” It can run locally, in a pre-commit hook, or as a GitHub Action and emits stable
exit codes, JSON, SARIF, and inline GitHub annotations.

The project deliberately fails closed when a file contains structures it cannot safely preserve.
It never rewrites application locale catalogs during a check.

## Quick start

Python 3.10 or newer is required.

```bash
python -m pip install -e .[dev]
l10n-sentinel --version
```

Check a target JSON or ARB catalog against its source:

```bash
l10n-sentinel check-locales \
  --source samples/locales/en.json \
  --target samples/locales/tr.json
```

Check several target locales in one deterministic run by listing them after `--target`:

```bash
l10n-sentinel check-locales --source locales/en.json --target locales/de.json locales/tr.json
```

Nested JSON objects are addressed with unambiguous JSON Pointer keys. ARB metadata keys beginning
with `@` are ignored. Duplicate JSON keys, arrays, numbers, booleans, and null catalog values are
rejected instead of being silently coerced. Catalogs are bounded to 16 MiB, 64 nesting levels,
100,000 messages, and 1,000,000 characters per message to limit accidental resource exhaustion.

## Findings

The locale contract currently reports:

- missing and orphan target keys;
- empty and unchanged translations;
- printf, brace, named-percent, and double-brace placeholder drift;
- HTML/XML tag-structure drift;
- leading/trailing whitespace and newline differences;
- unexpected bidirectional and invisible Unicode format characters;
- isolated Unicode surrogate code points.

Use `--fail-on error` (default), `--fail-on warning`, or `--fail-on never`. Exit codes are stable:

- `0`: no finding met the selected threshold;
- `1`: at least one finding met the threshold;
- `2`: input was malformed or could not be interpreted safely.

## Machine-readable reports

```bash
l10n-sentinel check-locales \
  --source locales/en.json \
  --target locales/tr.json \
  --output-format sarif \
  --report-file l10n-sentinel.sarif
```

Available output formats are `human`, `json`, `sarif`, and `github`. Report files are replaced
atomically so a failed run does not leave a partially written result. The versioned JSON contract
is documented in [`schemas/report.schema.json`](schemas/report.schema.json).

Repositories with existing findings can adopt the checker without hiding new regressions:

```bash
l10n-sentinel check-locales \
  --source locales/en.json \
  --target locales/tr.json \
  --write-baseline .l10n-sentinel-baseline.json

l10n-sentinel check-locales \
  --source locales/en.json \
  --target locales/tr.json \
  --baseline .l10n-sentinel-baseline.json
```

Baseline fingerprints contain finding identities, not source or translated text. Review baseline
changes like code: deleting a fingerprint re-enables that finding. Its schema is
[`schemas/baseline.schema.json`](schemas/baseline.schema.json).

## GitHub Action

Pin the action to a tagged release:

```yaml
- uses: ahmetmusab42-stack/l10n-sentinel@v0.3.0
  with:
    source: locales/en.json
    target: locales/tr.json
    fail-on: error
```

The action emits inline workflow annotations and exposes the machine-readable report path as
`steps.<id>.outputs.report`. Its definition is tested locally; the repository CI will verify it on
GitHub-hosted runners after publication.

## Native project and document checks

The secondary local workbench supports native project bundles, a conservative PO subset, and a
conservative XLIFF 1.2 subset:

```bash
l10n-sentinel validate --input project.json --output-format json
l10n-sentinel diff --baseline before.xlf --current after.xlf
l10n-sentinel sample
l10n-sentinel gui
```

| Format | Supported for round-trip | Rejected to prevent silent loss |
| --- | --- | --- |
| Native JSON | L10n Sentinel project bundles | Arbitrary application schemas |
| PO | Singular entries and Sentinel metadata | Plurals, external headers, flags, references, obsolete entries, unknown comments |
| XLIFF 1.2 | One flat file with plain-text trans-units | Inline elements, nested groups, multiple files, unknown metadata |

These limitations apply to the local import/export workbench, not to read-only JSON/ARB locale
contract checks.

## Development

```bash
ruff check src tests
coverage run -m unittest discover -s tests -v
coverage report
python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[ROADMAP.md](ROADMAP.md). Synthetic fixtures live under `samples/`; do not contribute customer or
private translation data.

## Project status

Version 0.3.0 is a release candidate. The CLI contract and data-safety behavior are tested, but the
project is not yet claiming broad format coverage or production adoption. Format support expands
only with redistributable real-world fixtures and regression tests.

Licensed under MPL-2.0.

Primary maintainer: [Ahmet Ercan](https://github.com/ahmetmusab42-stack).
