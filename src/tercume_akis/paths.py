from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from .catalog import PRODUCT_NAME, PRODUCT_SLUG


def default_data_root(*, environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    override = values.get("TERCUME_AKIS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform.startswith("win"):
        appdata = values.get("LOCALAPPDATA", "").strip()
        if appdata:
            return (Path(appdata) / PRODUCT_NAME).resolve()
    return (Path.home() / f".{PRODUCT_SLUG}").resolve()


def project_data_root(project_slug: str, *, environ: Mapping[str, str] | None = None) -> Path:
    return default_data_root(environ=environ) / project_slug
