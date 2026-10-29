"""Sharpless 2 catalog loader (VizieR VII/20).

Every row is classified as ``HII`` (Sharpless is a catalog of HII regions
by definition). The optional ``sharpless_crossref.csv`` side-input maps
selected Sh2 numbers to existing DSOs (e.g., ``Sh2-281 → NGC 1976``) —
when a mapping exists, the Sh2 number is attached as an additional
designation on the target DSO instead of creating a new DSO. Unmapped
rows create standalone DSOs with ``Sh2-<n>`` as their primary designation.

Constellation codes are derived from J2000 RA/Dec via astropy.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

logger = logging.getLogger("nightcrate.catalog_loader.sharpless")


def collect_sharpless(
    source: CatalogSource, crossref_path: Path | None
) -> tuple[list[dict[str, str | None]], dict[str, str], str]:
    """Parse Sharpless rows and its cross-reference side input without DB access."""
    crossref_hash = (
        file_sha256(crossref_path) if crossref_path is not None and crossref_path.exists() else "-"
    )
    effective_hash = f"{file_sha256(source.file_path)}:{crossref_hash}"
    crossref = load_crossref_csv(crossref_path) if crossref_path is not None else {}
    return list(parse_vizier_tsv(source.file_path)), crossref, effective_hash


def load_crossref_csv(path: Path) -> dict[str, str]:
    """Read ``sharpless_crossref.csv`` into a ``{sh2_number: target}`` map.

    Empty or missing files return an empty dict. Comment rows (``#…``)
    are skipped. Malformed rows are logged at WARNING and dropped.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header_seen = False
        for row in reader:
            if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                continue
            if not header_seen:
                header_seen = True
                continue
            if len(row) < 2:
                logger.warning("[sharpless] crossref row ignored (too few cols): %r", row)
                continue
            sh2, target = row[0].strip(), row[1].strip()
            if sh2 and target:
                out[sh2] = target
    return out
