"""Static registry of DSO catalog sources known to the loader.

v0.14.0 shipped two sources (OpenNGC + addendum, fetched from GitHub).
v0.15.0 adds VizieR-sourced catalogs (Sharpless, Barnard), a GitHub-
sourced 50 MGC catalog, and vendored NightCrate editorial CSVs
(augmentation + Sharpless crossref, plus the intentionally-empty Barnard
crossref for symmetry).

Most entries return regardless of whether the backing file exists on
disk — the loader emits ``status="missing"`` for absent files and the
UI surfaces a "Load" CTA in Admin → Catalogs. The two NightCrate
sources live in the Python package itself (``data/catalogs/nightcrate``)
so they're always available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from nightcrate.core.app_config import APP_DIR

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

VIZIER_BASE_URL = "https://vizier.cds.unistra.fr"
VIZIER_LICENSE = "CDS public"
CDS_CITATION = (
    "This research has made use of the VizieR catalogue access tool, "
    "CDS, Strasbourg, France (DOI: 10.26093/cds/vizier)."
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
    # Parser strategy identifier — dispatches to the right loader in
    # loader.py. One of: 'openngc', 'sharpless', 'barnard', 'mgc50',
    # 'augment', 'sharpless_crossref', 'barnard_crossref'.
    parser: str


def _load_version_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except _VERSION_JSON_ERRS:
        return {}


def read_installed_version(catalogs_root: Path) -> str | None:
    """Return the installed OpenNGC tag (e.g. ``"v20260307"``) or None."""
    info = _load_version_json(catalogs_root / "openngc" / "version.json")
    value = info.get("version")
    return str(value) if value else None


def _nightcrate_dir() -> Path:
    """Return the path to the vendored ``data/catalogs/nightcrate/`` folder.

    These files ship inside the Python package — no user-dir fallback,
    no GitHub fetch, no VizieR download. Use ``importlib.resources`` so
    the path resolves correctly both in source checkouts and installed
    wheels.
    """
    return Path(str(resources.files("nightcrate") / "data" / "catalogs" / "nightcrate"))


def _openngc_sources(catalogs_root: Path) -> list[CatalogSource]:
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


def _vizier_sources(catalogs_root: Path) -> list[CatalogSource]:
    vizier_dir = catalogs_root / "vizier"
    version_info = _load_version_json(vizier_dir / "version.json").get("files", {})

    def _version(filename: str) -> str | None:
        entry = version_info.get(filename) or {}
        return entry.get("fetch_date")

    return [
        CatalogSource(
            source_id="vizier_sharpless",
            category="vizier",
            display_name="Sharpless 2 (VizieR VII/20)",
            file_path=vizier_dir / "sharpless_VII_20.tsv",
            version=_version("sharpless_VII_20.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=(
                "Sharpless, S. 1959, ApJS, 4, 257 — A Catalogue of HII Regions. "
                "Retrieved via VizieR. " + CDS_CITATION
            ),
            parser="sharpless",
        ),
        CatalogSource(
            source_id="vizier_barnard",
            category="vizier",
            display_name="Barnard (VizieR VII/220)",
            file_path=vizier_dir / "barnard_VII_220.tsv",
            version=_version("barnard_VII_220.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=(
                "Barnard, E. E. 1927, A Photographic Atlas of Selected Regions of the "
                "Milky Way. Retrieved via VizieR. " + CDS_CITATION
            ),
            parser="barnard",
        ),
    ]


def _github_sources(catalogs_root: Path) -> list[CatalogSource]:
    """Sources fetched from GitHub raw-file URLs (not VizieR).

    Only 50 MGC lives here for v0.15.0 — OpenNGC has its own top-level
    entry in ``_openngc_sources`` since it's the flagship and predates
    this split.
    """
    mgc50_dir = catalogs_root / "github" / "50mgc"
    # The 50 MGC fetcher writes its own ``version.json`` in the mgc50 dir.
    info: dict = {}
    version_file = mgc50_dir / "version.json"
    if version_file.exists():
        try:
            info = json.loads(version_file.read_text(encoding="utf-8"))
        except _VERSION_JSON_ERRS:
            info = {}
    return [
        CatalogSource(
            source_id="github_50mgc",
            # Keep VizieR category — data origin is still VizieR; GitHub is
            # just the fetch path we found to be more reliable.
            category="vizier",
            display_name="50 Mpc Galaxy Catalog (Ohlson+ 2024, GitHub mirror)",
            file_path=mgc50_dir / "catalog.fits",
            version=info.get("fetched_at"),
            source_url="https://github.com/davidohlson/50MGC",
            license=VIZIER_LICENSE,
            attribution=(
                "Ohlson, D. et al. 2024, AJ, 167, 31 — The 50 Mpc Galaxy Catalog. "
                "Originally from VizieR J/AJ/167/31; fetched via the author's "
                "GitHub mirror for reliability. " + CDS_CITATION
            ),
            parser="mgc50",
        ),
    ]


def _nightcrate_sources() -> list[CatalogSource]:
    nightcrate_dir = _nightcrate_dir()
    return [
        CatalogSource(
            source_id="nightcrate_augment",
            category="nightcrate",
            display_name="NightCrate DSO augmentation",
            file_path=nightcrate_dir / "dso_augment.csv",
            version=None,
            source_url=None,
            license="MIT",
            attribution=(
                "NightCrate editorial augmentation data. MIT licensed. "
                "Distributed as part of NightCrate."
            ),
            parser="augment",
        ),
        CatalogSource(
            source_id="nightcrate_sharpless_crossref",
            category="nightcrate",
            display_name="NightCrate Sharpless crossref",
            file_path=nightcrate_dir / "sharpless_crossref.csv",
            version=None,
            source_url=None,
            license="MIT",
            attribution=(
                "NightCrate editorial crossref between Sharpless 2 and NGC/IC/Messier "
                "designations. MIT licensed."
            ),
            # Side-input consumed by the Sharpless loader itself; no DSOs
            # are created by this source directly.
            parser="sharpless_crossref",
        ),
        CatalogSource(
            source_id="nightcrate_barnard_crossref",
            category="nightcrate",
            display_name="NightCrate Barnard crossref (empty in v0.15.0)",
            file_path=nightcrate_dir / "barnard_crossref.csv",
            version=None,
            source_url=None,
            license="MIT",
            attribution=(
                "NightCrate editorial crossref for Barnard dark nebulae. Empty in "
                "v0.15.0 — dark nebulae and emission regions at the same line of "
                "sight are physically distinct and are not merged."
            ),
            parser="barnard_crossref",
        ),
    ]


def get_sources(catalogs_root: Path) -> list[CatalogSource]:
    """Return the full list of catalog sources in load order."""
    return [
        *_openngc_sources(catalogs_root),
        *_vizier_sources(catalogs_root),
        *_github_sources(catalogs_root),
        *_nightcrate_sources(),
    ]


def user_catalogs_root() -> Path:
    """User-writable catalogs directory under the OS app-data folder."""
    return APP_DIR / "catalogs"
