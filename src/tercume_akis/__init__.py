"""L10n Sentinel localization integrity package."""

from .catalog import DEFAULT_PROJECT_ID, PRODUCT_NAME, PRODUCT_SLUG, ProjectDefinition
from .formats import FORMAT_NAMES

__all__ = [
    "DEFAULT_PROJECT_ID",
    "FORMAT_NAMES",
    "PRODUCT_NAME",
    "PRODUCT_SLUG",
    "ProjectDefinition",
]

__version__ = "0.3.1"
