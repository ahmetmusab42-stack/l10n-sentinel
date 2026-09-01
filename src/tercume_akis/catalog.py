# ruff: noqa: I001

from dataclasses import dataclass


PRODUCT_SLUG = "l10n-sentinel"
PRODUCT_NAME = "L10n Sentinel"
DEFAULT_PROJECT_ID = "sample-project"


@dataclass(frozen=True)
class ProjectDefinition:
    slug: str
    name: str
    source_language: str
    target_language: str
    description: str = ""


DEFAULT_SAMPLE_PROJECT = ProjectDefinition(
    slug=DEFAULT_PROJECT_ID,
    name="Sample Website Localization",
    source_language="en",
    target_language="tr",
    description="Synthetic sample project for local testing and documentation.",
)
