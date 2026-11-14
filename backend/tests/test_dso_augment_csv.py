"""Shape checks for NightCrate's curated DSO augmentation file.

The loader skips unresolved rows with a warning, so a malformed row would
quietly change what users see. These checks keep the file well-formed; the
values themselves are verified against their sources when they are added.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import nightcrate

AUGMENT = Path(nightcrate.__file__).parent / "data" / "catalogs" / "nightcrate" / "dso_augment.csv"
HEADER = ["designation", "surface_brightness", "distance_pc", "notes"]


def _rows() -> list[list[str]]:
    with AUGMENT.open(encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if line.strip() and not line.lstrip().startswith("#")]
    rows = list(csv.reader(lines))
    assert rows[0] == HEADER
    return rows[1:]


def _section(title: str) -> list[list[str]]:
    """Rows after the comment line containing *title*, up to the next comment."""
    rows: list[list[str]] = []
    inside = False
    with AUGMENT.open(encoding="utf-8", newline="") as handle:
        for line in handle:
            if line.lstrip().startswith("#"):
                inside = title in line
                continue
            if inside and line.strip():
                rows.append(next(csv.reader([line])))
    return rows


def test_every_row_has_four_fields():
    bad = [row for row in _rows() if len(row) != 4]
    assert bad == []


def test_numbers_are_positive_or_empty():
    for designation, surface_brightness, distance_pc, _notes in _rows():
        for value in (surface_brightness, distance_pc):
            if value:
                assert float(value) > 0, designation


def test_designations_are_unique():
    keys = [re.sub(r"\s+", "", row[0]).casefold() for row in _rows()]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    assert duplicates == []


def test_every_distance_has_a_note():
    missing = [row[0] for row in _rows() if row[2] and not row[3].strip()]
    assert missing == []


def test_v051_distances_cite_a_published_source():
    rows = _section("Messier and Caldwell objects without a distance")
    assert len(rows) == 109
    uncited = [row[0] for row in rows if not re.search(r"\b(19|20)\d{2}\b", row[3])]
    assert uncited == []


def test_ic_3418_uses_the_virgo_cluster_distance():
    rows = {row[0]: row for row in _rows()}
    assert rows["IC 3418"][2] == "16500000"
    assert "Virgo" in rows["IC 3418"][3]


def test_resourced_rows_keep_their_surface_brightness():
    rows = {row[0]: row for row in _rows()}
    assert rows["NGC 6720"][1:3] == ["20.5", "783"]
    assert rows["NGC 6853"][1:3] == ["20.0", "387"]
    assert rows["NGC 7293"][1:3] == ["22.5", "199"]


def test_c50_is_keyed_by_ngc_2244():
    # OpenNGC folds NGC 2239 into NGC 2244 (C 50, the Rosette cluster); the
    # distance belongs to NGC 2244, so the row names it.
    rows = {row[0]: row for row in _rows()}
    assert rows["NGC 2244"][2] == "1420"
    assert "NGC 2239" not in rows
