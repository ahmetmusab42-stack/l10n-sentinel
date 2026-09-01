# Security Policy

## Supported versions

Security fixes are made on the latest tagged minor release. Until the first public tag, the
default branch is the only supported version.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting flow from the repository's **Security** tab. Do not
open a public issue containing an exploit, secret, credential, private URL, or customer data.

Please include the affected version, minimal reproduction, impact, and any suggested mitigation.
The maintainer will acknowledge a complete report within seven days and will coordinate disclosure
after a fix is available. These are response targets, not a bug-bounty or payment commitment.

## Security boundaries

L10n Sentinel is a local, non-networked parser and checker. Its primary untrusted inputs are locale
files, project bundles, and backup archives. Security-sensitive invariants include:

- no network calls, dynamic code execution, or shell evaluation while parsing;
- bounded, explicit format support rather than silent data loss;
- atomic report and export replacement;
- archive path validation and SQLite integrity checking before restore;
- no collection of locale contents, paths, identifiers, or usage telemetry.

Large-input resource exhaustion and parser differentials remain relevant risks. See the roadmap for
planned corpus and performance limits.
