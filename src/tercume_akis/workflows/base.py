from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any


class WorkflowValidationError(ValueError):
    pass


class WorkflowBase:
    @staticmethod
    def required(value: Any, label: str, *, maximum: int = 256) -> str:
        text = str(value).strip()
        if not text:
            raise WorkflowValidationError(f"{label} cannot be empty")
        if len(text) > maximum:
            raise WorkflowValidationError(f"{label} must be at most {maximum} characters")
        return text

    @staticmethod
    def iso_date(value: str, label: str) -> date:
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise WorkflowValidationError(f"{label} must use YYYY-MM-DD") from exc

    @staticmethod
    def validate_path(path: Path, label: str) -> Path:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise WorkflowValidationError(f"{label} was not found")
        return resolved
