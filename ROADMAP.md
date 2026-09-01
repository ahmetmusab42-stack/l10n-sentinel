# Roadmap

The roadmap is driven by reproducible maintainer problems and user-data safety, not format count.

## 0.3.x — public release and feedback

- Publish the Python distribution and GitHub Action from reproducible tags.
- Exercise JSON and ARB checks in external open-source repositories.
- Add JSON Schema documents for JSON output and configuration.
- Exercise baseline mode in repositories adopting the checker with known findings.
- Add property-based tests for nested catalog paths and Unicode edge cases.

## 0.4.x — pull-request maintenance workflow

- Attribute findings to changed keys in a pull request.
- Upload SARIF through a documented least-privilege workflow.
- Compare more than one target locale in a single deterministic run.
- Add a repository configuration file with explicit source and target paths.
- Publish performance fixtures and regression budgets.

## Later, after real user requests

- Read-only checks for Android XML, Apple String Catalogs, Fluent, and YAML.
- Safe support for PO plurals, flags, references, and comments.
- Safe XLIFF 1.2 inline elements and XLIFF 2.x.
- Editor integrations built on the same versioned finding schema.

New formats require redistributable fixtures, malformed-input tests, and a documented loss model
before they are advertised as supported.
