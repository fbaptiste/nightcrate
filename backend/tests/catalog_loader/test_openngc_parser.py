"""Unit tests for the OpenNGC CSV parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightcrate.catalog_loader.openngc_parser import (
    KNOWN_OBJ_TYPES,
    ParsedOpenNgcRow,
    parse_openngc,
    sexagesimal_dec_to_degrees,
    sexagesimal_ra_to_degrees,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "catalogs" / "openngc"


def _by_name(rows: list[ParsedOpenNgcRow]) -> dict[str, ParsedOpenNgcRow]:
    return {r.raw_name: r for r in rows}


def test_sexagesimal_ra_basic():
    assert sexagesimal_ra_to_degrees("00:00:00.0") == 0.0
    # 06h exactly = 90 degrees
    assert sexagesimal_ra_to_degrees("06:00:00.0") == pytest.approx(90.0)
    # Orion M42: 05:35:17.3 → 83.8221 deg
    assert sexagesimal_ra_to_degrees("05:35:17.3") == pytest.approx(83.8220833, abs=1e-6)


def test_sexagesimal_dec_basic():
    assert sexagesimal_dec_to_degrees("+00:00:00") == 0.0
    assert sexagesimal_dec_to_degrees("-05:23:28") == pytest.approx(-5.3911111, abs=1e-6)
    assert sexagesimal_dec_to_degrees("+41:16:09") == pytest.approx(41.269167, abs=1e-5)


def test_sexagesimal_handles_empty():
    assert sexagesimal_ra_to_degrees("") is None
    assert sexagesimal_dec_to_degrees("   ") is None


def test_sexagesimal_invalid_raises():
    with pytest.raises(ValueError):
        sexagesimal_ra_to_degrees("not a coord")
    with pytest.raises(ValueError):
        sexagesimal_dec_to_degrees("+45:30")


def test_parse_mini_fixture_skips_nonex():
    rows = list(parse_openngc(FIXTURE_DIR / "mini_NGC.csv"))
    names = [r.raw_name for r in rows]
    # IC0067 is NonEx — must be dropped entirely.
    assert "IC0067" not in names
    # IC0011 is Dup — must remain (loader handles merging).
    assert "IC0011" in names


def test_parse_marks_duplicates():
    rows = _by_name(list(parse_openngc(FIXTURE_DIR / "mini_NGC.csv")))
    assert rows["IC0011"].is_duplicate is True
    assert rows["NGC1976"].is_duplicate is False
    # Dup rows carry a cross-reference to the canonical NGC — "0281" stripped to "281".
    assert rows["IC0011"].ngc_cross_ref == "281"


def test_parse_fills_coordinates_and_type():
    rows = _by_name(list(parse_openngc(FIXTURE_DIR / "mini_NGC.csv")))
    m42 = rows["NGC1976"]
    assert m42.obj_type == "HII"
    assert m42.raw_obj_type is None
    assert m42.ra_deg == pytest.approx(83.82208, abs=1e-4)
    assert m42.dec_deg == pytest.approx(-5.39111, abs=1e-4)
    assert m42.constellation == "Ori"
    assert m42.messier_number == "42"
    assert m42.name_catalog == "ngc"
    assert m42.name_identifier == "1976"


def test_parse_unknown_type_falls_back_to_other():
    rows = _by_name(list(parse_openngc(FIXTURE_DIR / "mini_NGC.csv")))
    custom = rows["NGC1234"]
    # "Other" is a known type on its own; let's verify the vocabulary
    # handling by constructing a synthetic row with a truly unknown code.
    # First confirm the vocabulary includes 'Other':
    assert "Other" in KNOWN_OBJ_TYPES
    # The fixture uses 'Other' verbatim — so raw_obj_type should be None
    # (it wasn't mapped, it was the original).
    assert custom.obj_type == "Other"
    assert custom.raw_obj_type is None


def test_unknown_type_preserves_raw(tmp_path: Path):
    csv_content = (
        "Name;Type;RA;Dec;Const;MajAx;MinAx;PosAng;B-Mag;V-Mag;J-Mag;H-Mag;K-Mag;"
        "SurfBr;Hubble;Pax;Pm-RA;Pm-Dec;RadVel;Redshift;Cstar U-Mag;Cstar B-Mag;"
        "Cstar V-Mag;M;NGC;IC;Cstar Names;Identifiers;Common names;NED notes;"
        "OpenNGC notes;Sources\n"
        "NGC9999;QuasarFuture;00:00:00.0;+00:00:00;Ori;;;;;;;;;;;;;;;;;;;;;;;;;;;Type:99\n"
    )
    path = tmp_path / "unknown_type.csv"
    path.write_text(csv_content, encoding="utf-8")
    rows = list(parse_openngc(path))
    assert rows[0].obj_type == "Other"
    assert rows[0].raw_obj_type == "QuasarFuture"


def test_missing_required_column_raises(tmp_path: Path):
    path = tmp_path / "bad.csv"
    path.write_text("Name;RA;Dec\nNGC1;00:00:00;+00:00:00\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Type"):
        list(parse_openngc(path))


def test_bom_is_tolerated(tmp_path: Path):
    header = (
        "Name;Type;RA;Dec;Const;MajAx;MinAx;PosAng;B-Mag;V-Mag;J-Mag;H-Mag;K-Mag;"
        "SurfBr;Hubble;Pax;Pm-RA;Pm-Dec;RadVel;Redshift;Cstar U-Mag;Cstar B-Mag;"
        "Cstar V-Mag;M;NGC;IC;Cstar Names;Identifiers;Common names;NED notes;"
        "OpenNGC notes;Sources\n"
    )
    body = "NGC0001;G;00:00:00.0;+00:00:00;Ori;;;;;;;;;;;;;;;;;;;;;;;;;;;Type:1\n"
    path = tmp_path / "with_bom.csv"
    path.write_bytes("\ufeff".encode() + (header + body).encode())
    rows = list(parse_openngc(path))
    assert len(rows) == 1
    assert rows[0].raw_name == "NGC0001"


def test_messier_addendum_parses_name_prefix():
    rows = _by_name(list(parse_openngc(FIXTURE_DIR / "mini_addendum.csv")))
    m40 = rows["M040"]
    assert m40.name_catalog == "messier"
    assert m40.name_identifier == "40"
    assert m40.messier_number == "40"
    # Addendum's B033 → Barnard 33
    b33 = rows["B033"]
    assert b33.name_catalog == "barnard"
    assert b33.name_identifier == "33"


def test_addendum_dup_resolves_via_messier():
    rows = _by_name(list(parse_openngc(FIXTURE_DIR / "mini_addendum.csv")))
    m102 = rows["M102"]
    assert m102.is_duplicate is True
    # NGC/IC are empty but M=101 is populated.
    assert m102.ngc_cross_ref is None
    assert m102.ic_cross_ref is None
    assert m102.messier_number == "101"


def test_leading_zeros_stripped():
    rows = _by_name(list(parse_openngc(FIXTURE_DIR / "mini_NGC.csv")))
    # "042" in the Messier column → "42"
    assert rows["NGC1976"].messier_number == "42"
    # "0281" in NGC cross-ref → "281"
    assert rows["IC0011"].ngc_cross_ref == "281"


def test_row_hash_is_stable_across_parses():
    first = list(parse_openngc(FIXTURE_DIR / "mini_NGC.csv"))
    second = list(parse_openngc(FIXTURE_DIR / "mini_NGC.csv"))
    assert [r.row_hash for r in first] == [r.row_hash for r in second]
    # Different hashes for different rows:
    assert first[0].row_hash != first[1].row_hash
