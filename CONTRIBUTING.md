# Contributing

Thanks for improving L10n Sentinel.

## Before you open a pull request

- Keep changes focused.
- Add or update tests.
- Do not include secrets, customer data, or commercial artifacts.
- Preserve the offline-first, local-first architecture.

## Development workflow

```bash
python -m pip install -e .[dev]
python -m unittest discover -s tests -v
ruff check src tests
python -m build
```

## Good first contributions

- Add a failing fixture for a real-world localization edge case.
- Improve safe PO or XLIFF compatibility without silent data loss.
- Add a new integrity check with both positive and negative tests.
- Improve CLI diagnostics, JSON reports, and recovery guidance.
