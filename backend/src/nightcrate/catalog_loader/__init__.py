"""DSO catalog loader — populates the `dso` and `dso_designation` tables
from user-downloaded catalog source files (OpenNGC for v0.14.0)."""

from nightcrate.catalog_loader.loader import (
    CatalogLoadStatus,
    LoadSummary,
    SourceResult,
    load_catalogs,
)

__all__ = ["CatalogLoadStatus", "LoadSummary", "SourceResult", "load_catalogs"]
