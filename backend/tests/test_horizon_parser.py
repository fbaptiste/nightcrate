"""Tests for the horizon text parser."""

from pathlib import Path

import pytest

from nightcrate.services.horizon import (
    HorizonParseError,
    parse_horizon_text,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "horizons"


def test_parse_nina_canonical_example() -> None:
    text = """\
# N.I.N.A. horizon file
# Az  Alt
0  12
90 5
180 8
270 10
"""
    result = parse_horizon_text(text)
    assert [p[0] for p in result.points] == [0, 90, 180, 270]
    assert result.warnings == []


def test_parse_hash_comments_stripped() -> None:
    text = """\
# this is a header
0 10  # inline comment
90 20
"""
    result = parse_horizon_text(text)
    assert result.points == [(0.0, 10.0), (90.0, 20.0)]


def test_parse_semicolon_comments_stripped() -> None:
    text = """\
; APCC-style comment
0 10
90 20
"""
    result = parse_horizon_text(text)
    assert len(result.points) == 2


def test_parse_comma_separated() -> None:
    text = "0,10\n90,20\n"
    result = parse_horizon_text(text)
    assert result.points == [(0.0, 10.0), (90.0, 20.0)]


def test_parse_tab_separated() -> None:
    text = "0\t10\n90\t20\n"
    result = parse_horizon_text(text)
    assert result.points == [(0.0, 10.0), (90.0, 20.0)]


def test_parse_mixed_whitespace() -> None:
    text = "  0   10 \n90,\t20\n"
    result = parse_horizon_text(text)
    assert result.points == [(0.0, 10.0), (90.0, 20.0)]


def test_parse_negative_azimuth_normalized() -> None:
    # -90 should fold to 270
    text = "-90 10\n0 5\n"
    result = parse_horizon_text(text)
    # Sorted ascending by azimuth after normalization
    azimuths = [p[0] for p in result.points]
    assert 270.0 in azimuths
    assert 0.0 in azimuths


def test_parse_out_of_range_azimuth_rejected() -> None:
    with pytest.raises(HorizonParseError, match="azimuth"):
        parse_horizon_text("400 10\n0 5\n")


def test_parse_altitude_too_high_rejected() -> None:
    with pytest.raises(HorizonParseError, match="altitude"):
        parse_horizon_text("0 95\n90 5\n")


def test_parse_altitude_too_low_rejected() -> None:
    with pytest.raises(HorizonParseError, match="altitude"):
        parse_horizon_text("0 -10\n90 5\n")


def test_parse_altitude_mild_downslope_accepted() -> None:
    # -5 is the lower bound and should be valid
    result = parse_horizon_text("0 -5\n180 0\n")
    assert result.points[0][1] == -5.0


def test_parse_duplicate_azimuth_offset_with_warning() -> None:
    text = "180 5\n180 10\n0 0\n"
    result = parse_horizon_text(text)
    # After sort: 0, 180, 180 → offset second to 180.01
    azimuths = [p[0] for p in result.points]
    assert azimuths == [0.0, 180.0, 180.01]
    assert len(result.warnings) == 1
    assert "180" in result.warnings[0]


def test_parse_three_duplicate_azimuths_stack_offsets() -> None:
    text = "180 1\n180 2\n180 3\n0 0\n"
    result = parse_horizon_text(text)
    azimuths = [p[0] for p in result.points]
    assert azimuths == [0.0, 180.0, 180.01, 180.02]
    assert len(result.warnings) == 2


def test_parse_fewer_than_two_points_rejected() -> None:
    with pytest.raises(HorizonParseError, match="at least 2"):
        parse_horizon_text("90 10\n")


def test_parse_malformed_line_rejected() -> None:
    with pytest.raises(HorizonParseError, match="Line 2"):
        parse_horizon_text("0 10\nnot a number\n180 20\n")


def test_parse_empty_file_rejected() -> None:
    with pytest.raises(HorizonParseError, match="Empty"):
        parse_horizon_text("")


def test_parse_all_comments_rejected() -> None:
    with pytest.raises(HorizonParseError, match="Empty"):
        parse_horizon_text("# just\n# comments\n")


def test_parse_blank_lines_skipped() -> None:
    text = "\n0 10\n\n\n90 20\n\n"
    result = parse_horizon_text(text)
    assert result.points == [(0.0, 10.0), (90.0, 20.0)]


def test_parse_crlf_line_endings() -> None:
    text = "0 10\r\n90 20\r\n"
    result = parse_horizon_text(text)
    assert result.points == [(0.0, 10.0), (90.0, 20.0)]


def test_parse_single_token_rejected() -> None:
    with pytest.raises(HorizonParseError, match="expected 2"):
        parse_horizon_text("45\n90 10\n")


def test_parse_three_tokens_rejected() -> None:
    with pytest.raises(HorizonParseError, match="expected 2"):
        parse_horizon_text("45 10 extra\n90 20\n")


def test_parse_preserves_source_filename() -> None:
    result = parse_horizon_text("0 10\n90 20\n", source_filename="my_site.hrz")
    assert result.source_filename == "my_site.hrz"


# ── Theodolite CSV ────────────────────────────────────────────────────────────


def test_parse_theodolite_sample_fixture() -> None:
    """Parses the real Theodolite iPhone log shipped as a test fixture."""
    path = FIXTURE_DIR / "theodolite_sample.csv"
    text = path.read_text()
    result = parse_horizon_text(text, source_filename=path.name)
    # Sample has 88 data rows (89 lines incl header); some may collapse or offset
    assert len(result.points) >= 80
    # Every point must be within valid ranges
    for az, alt in result.points:
        assert 0 <= az < 360
        assert -5 <= alt <= 90
    # Sorted ascending by azimuth
    azimuths = [p[0] for p in result.points]
    assert azimuths == sorted(azimuths)


def test_parse_theodolite_minimal_synthetic() -> None:
    text = (
        "DATE_TIME,LAT_DEG,LON_DEG,POS_STRING,ALT,ALT_UNITS,DATUM,"
        "HDG_DEG,HDG_MILS,HDG_TYPE,VERT,HORIZ,VH_UNITS,NOTE\n"
        "2026.01.01_00.00.00,33.0,-111.0,x,1000,FEET,WGE,45,800,TRUE,25.0,0.5,DEG\n"
        "2026.01.01_00.00.01,33.0,-111.0,x,1000,FEET,WGE,180,3200,TRUE,10.0,0.2,DEG\n"
    )
    result = parse_horizon_text(text)
    # Sorted ascending: 45, 180
    assert result.points == [(45.0, 25.0), (180.0, 10.0)]


def test_parse_csv_missing_theodolite_columns_falls_through_and_rejects() -> None:
    # Without both HDG_DEG and VERT, the sniffer treats the file as generic
    # 2-column text, which then rejects the 3-token data row.
    text = "DATE_TIME,HDG_DEG,NOTE\n2026.01.01,45,x\n"
    with pytest.raises(HorizonParseError):
        parse_horizon_text(text)


def test_parse_theodolite_skips_rows_with_empty_fields() -> None:
    text = "HDG_DEG,VERT\n45,10\n,,\n180,5\n"
    result = parse_horizon_text(text)
    assert result.points == [(45.0, 10.0), (180.0, 5.0)]
