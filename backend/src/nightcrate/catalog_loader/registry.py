"""Static registry of DSO catalog sources known to the loader.

Each ``CatalogSource`` entry names a file on disk, the parser strategy it
should be read with, and the attribution metadata used by the frontend's
Attribution panel. For v0.14.0 we register two sources — OpenNGC's main
file and its addendum. VizieR-sourced catalogs and NightCrate editorial
CSVs will be added in later passes.

The registry always returns the full list of logical sources regardless
of whether the backing files exist on disk — it's the loader's job to
handle missing files (skipped with ``status="missing"``) and the fetch
flow's job to populate them from GitHub.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nightcrate.core.app_config import APP_DIR

# Module-level tuple constant — sidesteps the py314 ruff-format bug
# documented in CLAUDE.md "Gotchas" where `except (A, B):` gets its
# parens stripped into the Python 2 `except A, B:` form.
_VERSION_JSON_ERRS: tuple[type[BaseException], ...] = (
    json.JSONDecodeError,
    OSError,
    ValueError,
)

OPENNGC_SOURCE_URL = "https://github.com/mattiaverga/OpenNGC"
OPENNGC_LICENSE = "CC-BY-SA-4.0"
OPENNGC_CITATION = (
    "Verga, Mattia. OpenNGC — Database of NGC and IC objects. "
    "https://github.com/mattiaverga/OpenNGC"
)


@dataclass(frozen=True, slots=True)
class CatalogSource:
    source_id: str
    category: str  # 'openngc' | 'vizier' | 'nightcrate'
    display_name: str
    file_path: Path
    version: str | None
    source_url: str | None
    license: str | None
    attribution: str
    parser: str  # parser strategy identifier — currently only 'openngc'


def _load_version_json(path: Path) -> dict:
    """Read ``version.json`` or return an empty dict on any error."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except _VERSION_JSON_ERRS:
        return {}


def read_installed_version(catalogs_root: Path) -> str | None:
    """Return the installed OpenNGC tag (e.g., ``"v20260307"``) or None."""
    info = _load_version_json(catalogs_root / "openngc" / "version.json")
    value = info.get("version")
    return str(value) if value else None


def get_sources(catalogs_root: Path) -> list[CatalogSource]:
    """Return the list of registered catalog sources.

    *catalogs_root* is the base directory that contains per-source
    subdirectories (``openngc/``, future ``vizier/``, …). Entries are
    returned unconditionally even when their backing files are absent —
    the loader reports ``status="missing"`` for those.
    """
    openngc_dir = catalogs_root / "openngc"
    info = _load_version_json(openngc_dir / "version.json")
    version = info.get("version")

    return [
        CatalogSource(
            source_id="openngc",
            category="openngc",
            display_name="OpenNGC (NGC / IC / Messier)",
            file_path=openngc_dir / "NGC.csv",
            version=version,
            source_url=OPENNGC_SOURCE_URL,
            license=OPENNGC_LICENSE,
            attribution=OPENNGC_CITATION,
            parser="openngc",
        ),
        CatalogSource(
            source_id="openngc_addendum",
            category="openngc",
            display_name="OpenNGC addendum (non-NGC/IC objects)",
            file_path=openngc_dir / "addendum.csv",
            version=version,
            source_url=OPENNGC_SOURCE_URL,
            license=OPENNGC_LICENSE,
            attribution=OPENNGC_CITATION,
            parser="openngc",
        ),
    ]


def user_catalogs_root() -> Path:
    """User-writable catalogs directory under the OS app-data folder.

    Lives alongside the SQLite DB and ``config.json``. The directory is
    created lazily on the first successful fetch — do not assume it
    exists until the user has hit "Load from GitHub" in Admin.
    """
    return APP_DIR / "catalogs"
