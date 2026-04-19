"""Tests for horizon exporters and filename sanitization."""

import io
import zipfile

from nightcrate.services.horizon import (
    export_csv,
    export_nina_hrz,
    export_stellarium_zip,
    parse_horizon_text,
    sanitize_filename,
)

SAMPLE_POINTS = [(0.0, 12.0), (90.0, 5.5), (180.0, 8.0), (270.0, 10.25)]


# ── N.I.N.A. .hrz ─────────────────────────────────────────────────────────────


def test_nina_hrz_header_comments_and_data_lines() -> None:
    text = export_nina_hrz("Mesa Backyard", SAMPLE_POINTS)
    lines = text.strip().splitlines()
    assert lines[0].startswith("#")
    assert "Mesa Backyard" in lines[1]
    data = [line for line in lines if line and not line.startswith("#")]
    assert len(data) == 4
    assert data[0] == "0 12"
    assert data[1] == "90 5.5"
    assert data[3] == "270 10.25"


def test_nina_hrz_round_trips_through_parser() -> None:
    text = export_nina_hrz("Any Site", SAMPLE_POINTS)
    parsed = parse_horizon_text(text)
    assert parsed.points == SAMPLE_POINTS


def test_nina_hrz_ends_with_newline() -> None:
    text = export_nina_hrz("site", SAMPLE_POINTS)
    assert text.endswith("\n")


def test_nina_hrz_sorts_output_even_if_input_unsorted() -> None:
    unsorted = [(180.0, 5.0), (0.0, 10.0), (90.0, 7.0), (270.0, 3.0)]
    text = export_nina_hrz("site", unsorted)
    data = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert data == ["0 10", "90 7", "180 5", "270 3"]


def test_nina_hrz_formats_trailing_zeros_trimmed() -> None:
    text = export_nina_hrz("site", [(0.0, 10.0), (180.0, 5.0)])
    assert "10\n" in text
    assert "5\n" in text
    # Never "10.0" or "5.00"
    assert "10.00" not in text
    assert "5.00" not in text


# ── CSV ───────────────────────────────────────────────────────────────────────


def test_csv_has_header_and_all_rows() -> None:
    text = export_csv(SAMPLE_POINTS)
    lines = text.strip().splitlines()
    assert lines[0] == "azimuth_deg,altitude_deg"
    assert len(lines) == 1 + len(SAMPLE_POINTS)


def test_csv_round_trips_through_parser() -> None:
    # Skip the header line manually or let parser accept it? Parser uses
    # generic 2-col, which would reject the header. Drop it.
    text = export_csv(SAMPLE_POINTS)
    body = "\n".join(text.splitlines()[1:])
    parsed = parse_horizon_text(body)
    assert parsed.points == SAMPLE_POINTS


# ── Stellarium zip ────────────────────────────────────────────────────────────


def test_stellarium_zip_contains_expected_files() -> None:
    payload = export_stellarium_zip(
        "Mesa", SAMPLE_POINTS, latitude=33.46, longitude=-111.62, elevation_m=1877
    )
    with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
        names = set(zf.namelist())
        assert names == {"landscape.ini", "horizon.txt", "readme.txt"}
        ini = zf.read("landscape.ini").decode("utf-8")
        horizon = zf.read("horizon.txt").decode("utf-8")
    assert "name = Mesa" in ini
    assert "type = polygonal" in ini
    assert "latitude = 33.46" in ini
    assert "longitude = -111.62" in ini
    assert "altitude = 1877" in ini
    lines = [line for line in horizon.strip().splitlines() if line]
    assert len(lines) == len(SAMPLE_POINTS)
    assert lines[0] == "0 12"


def test_stellarium_zip_handles_none_elevation() -> None:
    payload = export_stellarium_zip(
        "site", SAMPLE_POINTS, latitude=33.0, longitude=-111.0, elevation_m=None
    )
    with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
        ini = zf.read("landscape.ini").decode("utf-8")
    assert "altitude = 0" in ini


# ── Filename sanitization ─────────────────────────────────────────────────────


def test_sanitize_filename_spaces_to_underscores() -> None:
    assert sanitize_filename("Mesa Backyard") == "mesa_backyard"


def test_sanitize_filename_strips_unsafe_chars() -> None:
    assert sanitize_filename("Site: North/South!") == "site_northsouth"


def test_sanitize_filename_collapses_repeated_underscores() -> None:
    assert sanitize_filename("A   B") == "a_b"


def test_sanitize_filename_lowercases() -> None:
    assert sanitize_filename("UPPER") == "upper"


def test_sanitize_filename_empty_after_strip_falls_back() -> None:
    assert sanitize_filename("!@#$") == "horizon"


def test_sanitize_filename_hyphens_preserved() -> None:
    assert sanitize_filename("north-site") == "north-site"
