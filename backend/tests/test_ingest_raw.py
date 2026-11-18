"""Camera-raw ingest, capture-time provenance and quality invalidation."""

from __future__ import annotations

import io
import os
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.api import ingest
from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services import raw_io, raw_support
from nightcrate.services.ingest_scanner import _read_image_metadata, parse_image_file
from tests.catalog_helpers import _frames, _make_project
from tests.fixtures.raw_fixtures import write_cfa_dng


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def _generated(path: Path, *, exif: dict[str, str] | None = None) -> Path:
    samples = np.arange(32 * 34, dtype=np.uint16).reshape(32, 34) + 512
    return write_cfa_dng(path, samples, exif=exif)


async def _scan(client: AsyncClient, project_id: int, folder: str | Path) -> dict:
    response = await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
    assert response.status_code == 201, response.text
    response = await client.post(f"/api/projects/{project_id}/ingest")
    assert response.status_code == 200, response.text
    return response.json()


async def test_raw_scan_catalogs_frames(client: AsyncClient, tmp_path: Path):
    folder = tmp_path / "Lights"
    folder.mkdir()
    _generated(
        folder / "Light_M31.dng",
        exif={
            "Exif.Photo.DateTimeOriginal": "2026:03:15 21:30:00",
            "Exif.Photo.OffsetTimeOriginal": "-07:00",
            "Exif.Photo.ExposureTime": "1/125",
            "Exif.Photo.ISOSpeedRatings": "800",
        },
    )
    project_id = await _make_project(client, "Raw scan")
    run = await _scan(client, project_id, folder)
    assert run["status"] == "completed"
    assert run["errors_count"] == 0

    row = (await _frames(client, project_id))[0]
    assert row["frame_type"] == "light"
    assert row["frame_type_basis"] == "file_name"
    assert row["iso"] == 800
    assert row["gain"] is None
    assert row["exposure_seconds"] == 0.008
    assert row["date_obs_utc"] == "2026-03-16T04:30:00+00:00"
    assert row["date_obs_source"] == "exif_offset"
    assert row["filter_name_source"] == "auto"
    assert row["camera_temp_c"] is None

    async with get_db() as conn:
        stored = await (
            await conn.execute(
                "SELECT fits_header_json, file_metadata_json FROM sub_frame WHERE id = ?",
                (row["id"],),
            )
        ).fetchone()
    assert stored["fits_header_json"] == "{}"
    assert stored["file_metadata_json"] is not None


def test_raw_scan_layout_never_reads_full_pixel_or_colour_arrays(monkeypatch):
    import rawpy

    metadata = raw_io.RawMetadata(
        captured_local=None,
        utc_offset=None,
        time_source="none",
        exposure_s=1.0,
        iso=800,
        make="Fixture",
        model="Metadata only",
        body_serial=None,
        lens=None,
        lens_serial=None,
        focal_length_mm=None,
        orientation=None,
        camera_temp_c=None,
        sensor_temp_c=None,
        compression=None,
        cards=[],
    )

    class FakeRaw:
        sizes = SimpleNamespace(left_margin=1, top_margin=1, width=20, height=10)
        raw_pattern = np.array([[0, 1], [1, 2]], dtype=np.uint8)
        color_desc = b"RGBG"
        black_level_per_channel = (64, 64, 64, 64)
        white_level = 4095

        @property
        def raw_image_visible(self):
            raise AssertionError("scan copied the full raw image")

        @property
        def raw_colors_visible(self):
            raise AssertionError("scan copied the full colour map")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(raw_io, "read_raw_metadata", lambda _source: metadata)
    monkeypatch.setattr(rawpy, "imread", lambda _source: FakeRaw())
    scan, _header, file_metadata = _read_image_metadata(io.BytesIO(b"fixture"), "raw")
    assert (scan["image_width"], scan["image_height"]) == (20, 10)
    assert file_metadata["pattern"] == ("BG", "GR")


async def test_fits_unchanged(client: AsyncClient, tmp_path: Path):
    """FITS keeps its existing capture time, with file time as the fallback."""
    folder = tmp_path / "fits"
    folder.mkdir()
    with_header = folder / "Light_header.fits"
    without_header = folder / "Light_file_time.fits"

    header_hdu = fits.PrimaryHDU(np.full((8, 8), 1000, dtype=np.uint16))
    header_hdu.header["IMAGETYP"] = "LIGHT"
    header_hdu.header["DATE-OBS"] = "2026-03-15T23:00:00"
    header_hdu.writeto(with_header)
    file_time_hdu = fits.PrimaryHDU(np.full((8, 8), 1001, dtype=np.uint16))
    file_time_hdu.header["IMAGETYP"] = "LIGHT"
    file_time_hdu.writeto(without_header)
    epoch = datetime(2026, 4, 5, 6, 7, tzinfo=UTC).timestamp()
    os.utime(without_header, (epoch, epoch))

    project_id = await _make_project(client, "FITS capture time")
    run = await _scan(client, project_id, folder)
    assert run["errors_count"] == 0
    rows = {Path(row["path"]).name: row for row in await _frames(client, project_id)}
    assert rows[with_header.name]["date_obs_source"] == "header"
    assert rows[with_header.name]["date_obs_utc"] == "2026-03-15T23:00:00+00:00"
    assert rows[without_header.name]["date_obs_source"] == "file_time"
    assert rows[without_header.name]["date_obs_utc"] == "2026-04-05T06:07:00+00:00"


async def test_catalog_response_fields(client: AsyncClient, tmp_path: Path):
    folder = tmp_path / "Lights"
    folder.mkdir()
    _generated(
        folder / "Light_fields.dng",
        exif={
            "Exif.Photo.DateTimeOriginal": "2026:03:15 21:30:00",
            "Exif.Photo.OffsetTimeOriginal": "-07:00",
            "Exif.Photo.ISOSpeedRatings": "800",
        },
    )
    project_id = await _make_project(client, "Raw catalog fields")
    await _scan(client, project_id, folder)

    row = (await _frames(client, project_id))[0]
    assert {
        "iso": row["iso"],
        "camera_temp_c": row["camera_temp_c"],
        "date_obs_source": row["date_obs_source"],
        "frame_type_basis": row["frame_type_basis"],
        "filter_name_source": row["filter_name_source"],
        "quality_units": row["quality_units"],
    } == {
        "iso": 800,
        "camera_temp_c": None,
        "date_obs_source": "exif_offset",
        "frame_type_basis": "file_name",
        "filter_name_source": "auto",
        "quality_units": None,
    }


@pytest.mark.parametrize(
    ("meta", "geo_tz", "expected", "source"),
    [
        ({"date_obs": "2026-03-15T21:30:00"}, None, "2026-03-15T21:30:00+00:00", "header"),
        (
            {
                "captured_local": "2026-03-15T21:30:00",
                "utc_offset_minutes": -420,
                "time_source": "exif_offset",
            },
            None,
            "2026-03-16T04:30:00+00:00",
            "exif_offset",
        ),
        (
            {
                "captured_local": "2026-03-15T21:30:00",
                "utc_offset_minutes": 60,
                "time_source": "maker_note",
            },
            None,
            "2026-03-15T20:30:00+00:00",
            "maker_note",
        ),
        (
            {"captured_local": "2026-03-08T03:30:00", "time_source": "none"},
            "America/New_York",
            "2026-03-08T07:30:00+00:00",
            "estimated_project_zone",
        ),
        ({}, None, "2026-03-15T20:00:00+00:00", "file_time"),
    ],
)
def test_capture_time_sources(meta, geo_tz, expected, source):
    assert ingest._coerce_date_obs(meta, "2026-03-15T20:00:00+00:00", geo_tz) == (
        expected,
        source,
    )


@pytest.mark.parametrize(
    ("header", "meta", "expected", "source"),
    [
        (
            "05/01/23",
            {"captured_local": "2026-03-15T21:30:00", "utc_offset_minutes": -420},
            "2026-03-16T04:30:00+00:00",
            "exif_offset",
        ),
        ("2023-01-05 21:03", {}, "2023-01-05T21:03:00+00:00", "header"),
        ("", {}, "2026-03-15T20:00:00+00:00", "file_time"),
    ],
)
def test_invalid_or_partial_header_dates_fall_through(header, meta, expected, source):
    assert ingest._coerce_date_obs(
        {"date_obs": header, **meta}, "2026-03-15T20:00:00+00:00", None
    ) == (expected, source)


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="time.tzset is unavailable")
def test_capture_time_uses_computer_zone_rules_for_capture_date(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        assert ingest._coerce_date_obs(
            {"captured_local": "2026-01-15T22:00:00"},
            "2026-01-15T20:00:00+00:00",
            None,
        ) == ("2026-01-16T03:00:00+00:00", "estimated_computer_zone")
        assert ingest._coerce_date_obs(
            {"captured_local": "2026-07-15T22:00:00"},
            "2026-07-15T20:00:00+00:00",
            None,
        ) == ("2026-07-16T02:00:00+00:00", "estimated_computer_zone")
    finally:
        monkeypatch.undo()
        time.tzset()


async def test_raw_without_capture_time_uses_archive_file_time(client: AsyncClient, tmp_path: Path):
    raw = _generated(tmp_path / "Light_no_time.dng")
    archive = tmp_path / "capture.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(raw, "Lights/Light_no_time.dng")
    epoch = datetime(2026, 4, 5, 6, 7, tzinfo=UTC).timestamp()
    os.utime(archive, (epoch, epoch))

    project_id = await _make_project(client, "Archive raw time")
    run = await _scan(client, project_id, archive)
    assert run["errors_count"] == 0
    row = (await _frames(client, project_id))[0]
    assert row["date_obs_source"] == "file_time"
    assert row["date_obs_utc"] == "2026-04-05T06:07:00+00:00"


async def test_raw_in_zip_scans(client: AsyncClient, tmp_path: Path):
    raw = _generated(
        tmp_path / "Dark_001.dng",
        exif={"Exif.Photo.DateTimeOriginal": "2026:03:15 21:30:00"},
    )
    archive = tmp_path / "raw.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(raw, "Darks/Dark_001.dng")
    project_id = await _make_project(client, "Raw archive")
    run = await _scan(client, project_id, archive)
    assert run["errors_count"] == 0
    row = (await _frames(client, project_id))[0]
    assert row["frame_type"] == "dark"
    assert row["path"] == f"{archive}::Darks/Dark_001.dng"


async def test_unsupported_raw_listed_uncataloged(client: AsyncClient, tmp_path: Path):
    folder = tmp_path / "Lights"
    folder.mkdir()
    (folder / "Light_bad.cr3").write_bytes(b"not a camera raw")
    project_id = await _make_project(client, "Unsupported raw")
    run = await _scan(client, project_id, folder)
    assert run["errors_count"] == 1
    listing = (await client.get(f"/api/projects/{project_id}/catalog/uncataloged")).json()
    assert listing["files"][0]["reason"] == "unsupported"


async def test_raw_unavailable_listed_with_reason(client: AsyncClient, tmp_path: Path, monkeypatch):
    folder = tmp_path / "Lights"
    folder.mkdir()
    _generated(folder / "Light_001.dng")
    project_id = await _make_project(client, "Unavailable raw")

    async def one_worker():
        return SimpleNamespace(max_worker_cores=1)

    monkeypatch.setattr(ingest, "get_settings", one_worker)
    monkeypatch.setattr(
        raw_support,
        "require",
        lambda: (_ for _ in ()).throw(
            raw_support.RawUnavailable("Raw files can't be read on this computer")
        ),
    )
    # raw_io imported require by name; patch that binding as well.
    monkeypatch.setattr("nightcrate.services.raw_io.require", raw_support.require)

    run = await _scan(client, project_id, folder)
    assert run["errors_count"] == 1
    listing = (await client.get(f"/api/projects/{project_id}/catalog/uncataloged")).json()
    assert listing["files"][0]["reason"] == "unsupported"
    assert listing["files"][0]["message"] == "Raw files can't be read on this computer"


async def test_sessions_group_by_iso(client: AsyncClient):
    project_id = await _make_project(client, "ISO sessions")
    async with get_db() as conn:
        for iso in (800, 1600):
            await conn.execute(
                "INSERT INTO sub_frame (project_id, content_hash, frame_type, exposure_seconds, "
                "iso, date_obs_utc) VALUES (?, ?, 'light', 60, ?, '2026-03-15T23:00:00Z')",
                (project_id, f"iso-{iso}", iso),
            )
        from nightcrate.services.session_derivation import derive_sessions

        await derive_sessions(conn, project_id, tz_name="UTC")
        await conn.commit()
    sessions = (await client.get(f"/api/projects/{project_id}/sessions")).json()
    assert sorted(row["iso"] for row in sessions) == [800, 1600]


async def test_rescan_clears_old_quality_on_new_mosaic(client: AsyncClient, tmp_path: Path):
    folder = tmp_path / "mosaic"
    folder.mkdir()
    path = folder / "Light_001.fits"
    hdu = fits.PrimaryHDU(np.full((8, 8), 1000, dtype=np.uint16))
    hdu.header["IMAGETYP"] = "LIGHT"
    hdu.header["EXPTIME"] = 60
    hdu.header["DATE-OBS"] = "2026-03-15T23:00:00"
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.writeto(path)
    project_id = await _make_project(client, "Quality invalidation")
    await _scan(client, project_id, folder)
    frame = (await _frames(client, project_id))[0]
    async with get_db() as conn:
        await conn.execute(
            "UPDATE sub_frame SET median_adu = 100, quality_analyzed_at = '2026-03-16', "
            "quality_status = 'ok', quality_method = NULL WHERE id = ?",
            (frame["id"],),
        )
        await conn.commit()
    response = await client.post(f"/api/projects/{project_id}/ingest")
    assert response.status_code == 200
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT median_adu, quality_analyzed_at, quality_status "
                "FROM sub_frame WHERE id = ?",
                (frame["id"],),
            )
        ).fetchone()
    assert tuple(row) == (None, None, None)


def test_parse_image_file_exposes_xisf_storage_metadata(tmp_path: Path):
    """The scanner persists sample format/bounds for future method changes."""
    from tests.test_xisf_io import _make_xisf

    path = tmp_path / "Light_001.xisf"
    values = np.arange(8, dtype=np.uint16)
    path.write_bytes(_make_xisf(4, 2, 1, "UInt16", values.tobytes(), bounds="1000:5000"))
    result = parse_image_file(str(path))
    assert result["file_type"] == "xisf"
    assert result["raw_header"]["XISF:SAMPLEFORMAT"] == "UInt16"
    assert result["raw_header"]["XISF:BOUNDS"] == "1000:5000"
