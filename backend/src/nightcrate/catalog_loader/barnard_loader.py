"""Barnard dark-nebula catalog loader (VizieR VII/220).

Every row creates a standalone DSO with ``obj_type = 'DrkN'``. Unlike
Sharpless, Barnard does NOT crossref-merge onto existing DSOs — dark
nebulae and emission regions at the same line of sight are physically
distinct objects and should not be conflated.

Constellation codes are derived from J2000 RA/Dec via astropy.
"""

from __future__ import annotations

import re

from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

# Barnard identifiers can carry letter suffixes (e.g., ``33a``). We
# normalise leading zeros off the numeric prefix while keeping any suffix.
_BARN_ID_RE = re.compile(r"^0*(\d+)(.*)$")


def _normalise_barn_id(raw: str) -> str:
    match = _BARN_ID_RE.match(raw)
    if match is None:
        return raw
    digits, suffix = match.groups()
    return (digits.lstrip("0") or "0") + (suffix or "")


def collect_barnard(source: CatalogSource) -> tuple[list[dict[str, str | None]], str]:
    """Parse a Barnard source without reading or writing the database."""
    return list(parse_vizier_tsv(source.file_path)), file_sha256(source.file_path)
