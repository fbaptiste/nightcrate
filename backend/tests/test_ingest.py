"""Tests for the directory-scan ingest pipeline (v0.40.0).

Two layers:
  * Pure helpers (classification, stack detection, session formation) — no DB.
  * End-to-end API flow against a temp folder of synthetic FITS files: folder
    binding, ingest, idempotent re-ingest, catalog summary/frames, partial
    equipment (NULL FKs), and master routing to processed_image.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.api.ingest import _observing_window_utc
from nightcrate.main import app
from nightcrate.services.ingest_classify import (
    CATEGORY_LOG,
    CATEGORY_OTHER,
    CATEGORY_PROCESSED,
    CATEGORY_PXIPROJECT,
    CATEGORY_SUB,
    classify_extension,
    classify_frame,
    is_stack,
)
from nightcrate.services.ingest_scanner import (
    parse_image_file,
    scan_directory,
)
from nightcrate.services.ingest_sessions import observing_night, session_key

# ── Pure: extension classification ───────────────────────────────────────────


class TestClassifyExtension:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("M31_Ha_001.fits", CATEGORY_SUB),
            ("frame.fit", CATEGORY_SUB),
            ("frame.fts", CATEGORY_SUB),
            ("stack.xisf", CATEGORY_SUB),
            ("final.tif", CATEGORY_OTHER),
            ("export.png", CATEGORY_OTHER),
            ("readme.md", CATEGORY_OTHER),
            ("PHD2_GuideLog_2026-03-07.txt", CATEGORY_LOG),
            ("Autorun_Log_2026.txt", CATEGORY_LOG),
            ("session.autofocus", CATEGORY_LOG),
        ],
    )
    def test_extension(self, name, expected):
        assert classify_extension(name) == expected

    def test_pxiproject_dir(self):
        assert classify_extension("MyProject.pxiproject", is_dir=True) == CATEGORY_PXIPROJECT
        assert classify_extension("MyProject.pxiproject", is_dir=False) == CATEGORY_PXIPROJECT


# ── Pure: frame classification + stack detection ─────────────────────────────


class TestClassifyFrame:
    @pytest.mark.parametrize(
        ("imagetyp", "expected"),
        [
            ("LIGHT", "light"),
            ("Light Frame", "light"),
            ("DARK", "dark"),
            ("FLAT", "flat"),
            ("BIAS", "bias"),
            ("Bias Frame", "bias"),
        ],
    )
    def test_light_dark_flat_bias(self, imagetyp, expected):
        route, frame_type = classify_frame({}, {"IMAGETYP": imagetyp})
        assert route == CATEGORY_SUB
        assert frame_type == expected

    def test_flat_dark(self):
        route, frame_type = classify_frame({}, {"IMAGETYP": "FlatDark"})
        assert route == CATEGORY_SUB
        assert frame_type == "dark_flat"

    def test_unknown_imagetyp(self):
        route, frame_type = classify_frame({}, {"IMAGETYP": "Whatever"})
        assert route == CATEGORY_SUB
        assert frame_type == "unknown"

    def test_missing_imagetyp(self):
        route, frame_type = classify_frame({}, {})
        assert route == CATEGORY_SUB
        assert frame_type == "unknown"

    def test_stack_by_ncombine(self):
        assert is_stack({}, {"IMAGETYP": "Light", "NCOMBINE": "25"}) is True
        route, _ = classify_frame({}, {"IMAGETYP": "Light", "NCOMBINE": "25"})
        assert route == CATEGORY_PROCESSED

    def test_stack_by_stackcnt(self):
        assert is_stack({}, {"STACKCNT": "40"}) is True

    def test_stack_by_master_imagetyp(self):
        assert is_stack({}, {"IMAGETYP": "Master Flat"}) is True
        route, frame_type = classify_frame({}, {"IMAGETYP": "Master Flat"})
        assert route == CATEGORY_PROCESSED

    def test_single_frame_not_stack(self):
        assert is_stack({}, {"IMAGETYP": "Light", "NCOMBINE": "1"}) is False
        assert is_stack({}, {"IMAGETYP": "Light"}) is False


# ── Pure: session formation ──────────────────────────────────────────────────


class TestSessionFormation:
    def test_evening_and_predawn_same_night(self):
        # 22:00 and 02:00-next-day belong to the same observing night.
        a = observing_night("2026-03-15T22:00:00+00:00", "UTC")
        b = observing_night("2026-03-16T02:00:00+00:00", "UTC")
        assert a == b == "2026-03-15"

    def test_afternoon_starts_new_night(self):
        # Noon is the boundary: 11:00 belongs to the prior night, 13:00 to the new.
        assert observing_night("2026-03-16T11:00:00+00:00", "UTC") == "2026-03-15"
        assert observing_night("2026-03-16T13:00:00+00:00", "UTC") == "2026-03-16"

    def test_timezone_shifts_night(self):
        # 04:00 UTC in Phoenix (UTC-7) is 21:00 the previous evening → prior night.
        night = observing_night("2026-03-16T04:00:00+00:00", "America/Phoenix")
        assert night == "2026-03-15"

    def test_invalid_tz_falls_back_to_utc(self):
        assert observing_night("2026-03-15T22:00:00+00:00", "Not/AZone") == "2026-03-15"

    def test_session_key_separates_rigs(self):
        k_none = session_key(None, "2026-03-15T22:00:00+00:00", "UTC")
        k_rig = session_key(3, "2026-03-15T22:00:00+00:00", "UTC")
        assert k_none == (None, "2026-03-15")
        assert k_rig == (3, "2026-03-15")
        assert k_none != k_rig

    def test_observing_window_utc_uses_site_offset(self):
        # Local noon-to-noon in the site tz, converted to UTC — NOT a literal
        # noon-UTC stamp (the old bug). Phoenix is UTC-7 → local noon = 19:00 UTC.
        start, end = _observing_window_utc("2026-03-15", "America/Phoenix")
        assert start == "2026-03-15T19:00:00+00:00"
        assert end == "2026-03-16T19:00:00+00:00"

    def test_observing_window_utc_defaults_to_utc(self):
        start, end = _observing_window_utc("2026-03-15", None)
        assert start == "2026-03-15T12:00:00+00:00"
        assert end == "2026-03-16T12:00:00+00:00"

    def test_observing_window_utc_bad_zone_falls_back(self):
        start, _ = _observing_window_utc("2026-03-15", "Not/AZone")
        assert start == "2026-03-15T12:00:00+00:00"


# ── Scanner + worker (no DB) ─────────────────────────────────────────────────


class TestScanner:
    def test_scan_skips_hidden_and_classifies(self, tmp_path: Path):
        (tmp_path / "sub").mkdir()
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "sub" / "light.fits").write_bytes(b"x")
        (tmp_path / "notes.txt").write_text("n")
        (tmp_path / ".secret.fits").write_bytes(b"x")
        (tmp_path / "Proj.pxiproject").mkdir()

        entries = {e.name: e for e in scan_directory(str(tmp_path))}
        assert "light.fits" in entries
        assert entries["light.fits"].category == CATEGORY_SUB
        assert entries["Proj.pxiproject"].category == CATEGORY_PXIPROJECT
        # Hidden file/dir excluded; pxiproject not descended into.
        assert ".secret.fits" not in entries
        assert all(
            not e.name.startswith(".") or e.name.endswith(".pxiproject") for e in entries.values()
        )

    def test_scan_missing_dir_returns_empty(self, tmp_path: Path):
        assert scan_directory(str(tmp_path / "nope")) == []

    def test_parse_image_file_reads_header_and_hash(self, tmp_path: Path):
        path = tmp_path / "frame.fits"
        data = np.full((8, 8), 7, dtype=np.uint16)
        hdu = fits.PrimaryHDU(data)
        hdu.header["IMAGETYP"] = "LIGHT"
        hdu.header["EXPTIME"] = 120.0
        hdu.header["FILTER"] = "Ha"
        hdu.writeto(path)

        result = parse_image_file(str(path))
        assert result["error"] is None
        assert len(result["content_hash"]) == 64  # sha256 hex
        assert result["raw_header"]["IMAGETYP"] == "LIGHT"
        assert result["meta"]["frame_type"] == "light"
        assert result["meta"]["exposure_time"] == "120.0"

    def test_parse_image_file_records_error(self, tmp_path: Path):
        bad = tmp_path / "broken.fits"
        bad.write_bytes(b"not a real fits file")
        result = parse_image_file(str(bad))
        assert result["error"] is not None
        assert "content_hash" not in result


# ── End-to-end API ───────────────────────────────────────────────────────────


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


_PIXEL_SEED = __import__("itertools").count(1)


def _write_fits(
    path: Path,
    *,
    imagetyp: str,
    filt: str | None = None,
    exptime: float = 300.0,
    extra: dict | None = None,
) -> None:
    # Unique pixel data per file so each gets a distinct content hash (real subs
    # are never byte-identical; identical data would correctly dedupe on hash).
    data = np.full((8, 8), next(_PIXEL_SEED), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    hdu.header["IMAGETYP"] = imagetyp
    hdu.header["EXPTIME"] = exptime
    hdu.header["GAIN"] = 100
    hdu.header["CCD-TEMP"] = -9.8
    hdu.header["SET-TEMP"] = -10.0
    hdu.header["XBINNING"] = 1
    hdu.header["YBINNING"] = 1
    hdu.header["INSTRUME"] = "ZWO ASI2600MM Pro"
    hdu.header["TELESCOP"] = "Celestron C11"
    hdu.header["DATE-OBS"] = "2026-03-15T23:30:00"
    hdu.header["OBJECT"] = "Tulip Nebula"
    if filt is not None:
        hdu.header["FILTER"] = filt
    for k, v in (extra or {}).items():
        hdu.header[k] = v
    hdu.writeto(path, overwrite=True)


@pytest.fixture
def imaging_folder(tmp_path: Path) -> Path:
    """A folder mimicking a real capture layout (folder names are decoys)."""
    folder = tmp_path / "Tulip"
    (folder / "raw" / "H").mkdir(parents=True)
    (folder / "calibration" / "darks").mkdir(parents=True)
    (folder / "calibration" / "flats").mkdir(parents=True)
    (folder / "masters").mkdir(parents=True)

    _write_fits(folder / "raw" / "H" / "light_001.fits", imagetyp="LIGHT", filt="Ha")
    _write_fits(folder / "raw" / "H" / "light_002.fits", imagetyp="LIGHT", filt="Ha")
    # A dark mislabeled into a folder called "darks" but IMAGETYP is authoritative.
    _write_fits(folder / "calibration" / "darks" / "dark_001.fits", imagetyp="DARK")
    _write_fits(folder / "calibration" / "flats" / "flat_001.fits", imagetyp="FLAT", filt="Ha")
    # A master stack routes to processed_image.
    _write_fits(
        folder / "masters" / "master_ha.fits",
        imagetyp="LIGHT",
        filt="Ha",
        extra={"NCOMBINE": 25},
    )
    # Non-image files.
    (folder / "PHD2_GuideLog_2026-03-15.txt").write_text("guiding\n")
    (folder / "notes.md").write_text("hello\n")
    (folder / "MyProject.pxiproject").mkdir()
    return folder


async def _make_project(client: AsyncClient, name: str = "Ingest Test") -> int:
    resp = await client.post("/api/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestFolderBinding:
    async def test_add_first_folder_is_primary(self, client):
        pid = await _make_project(client, "FolderProj")
        resp = await client.post(f"/api/projects/{pid}/folders", json={"path": "/data/a"})
        assert resp.status_code == 201, resp.text
        assert resp.json()["is_primary"] is True

    async def test_second_folder_not_primary_and_switch(self, client):
        pid = await _make_project(client, "FolderProj2")
        await client.post(f"/api/projects/{pid}/folders", json={"path": "/data/a"})
        r2 = await client.post(f"/api/projects/{pid}/folders", json={"path": "/data/b"})
        assert r2.json()["is_primary"] is False
        fid2 = r2.json()["id"]
        rp = await client.put(f"/api/projects/{pid}/folders/{fid2}/primary")
        assert rp.json()["is_primary"] is True
        listing = (await client.get(f"/api/projects/{pid}/folders")).json()
        primaries = [f for f in listing if f["is_primary"]]
        assert len(primaries) == 1 and primaries[0]["id"] == fid2

    async def test_duplicate_folder_409(self, client):
        pid = await _make_project(client, "FolderProj3")
        await client.post(f"/api/projects/{pid}/folders", json={"path": "/data/a"})
        dup = await client.post(f"/api/projects/{pid}/folders", json={"path": "/data/a"})
        assert dup.status_code == 409

    async def test_remove_folder(self, client):
        pid = await _make_project(client, "FolderProj4")
        r = await client.post(f"/api/projects/{pid}/folders", json={"path": "/data/a"})
        fid = r.json()["id"]
        rd = await client.delete(f"/api/projects/{pid}/folders/{fid}")
        assert rd.status_code == 204
        assert (await client.get(f"/api/projects/{pid}/folders")).json() == []

    async def test_ingest_without_folders_422(self, client):
        pid = await _make_project(client, "NoFolders")
        resp = await client.post(f"/api/projects/{pid}/ingest")
        assert resp.status_code == 422


class TestIngestEndToEnd:
    async def test_ingest_classifies_and_counts(self, client, imaging_folder):
        pid = await _make_project(client, "E2E")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(imaging_folder)})

        resp = await client.post(f"/api/projects/{pid}/ingest")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "completed"
        assert body["errors_count"] == 0
        # 2 lights + 1 dark + 1 flat + 1 master = 5 header-bearing inserts.
        assert body["subs_inserted"] == 5

        summary = (await client.get(f"/api/projects/{pid}/catalog/summary")).json()
        assert summary["lights"] == 2
        assert summary["darks"] == 1
        assert summary["flats"] == 1
        assert summary["processed"] == 1  # the NCOMBINE master
        assert summary["logs"] == 1
        assert summary["pxiprojects"] == 1
        assert summary["other"] == 1  # notes.md
        # One observing night, one rig bucket (NULL) → one session.
        assert summary["sessions"] == 1

    async def test_idempotent_reingest(self, client, imaging_folder):
        pid = await _make_project(client, "Idem")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(imaging_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        first = (await client.get(f"/api/projects/{pid}/catalog/summary")).json()

        second_run = (await client.post(f"/api/projects/{pid}/ingest")).json()
        assert second_run["subs_inserted"] == 0
        assert second_run["subs_updated"] == 5
        second = (await client.get(f"/api/projects/{pid}/catalog/summary")).json()
        # Counts must not grow on re-ingest.
        assert second["lights"] == first["lights"]
        assert second["darks"] == first["darks"]
        assert second["processed"] == first["processed"]
        assert second["sessions"] == first["sessions"]

    async def test_ingest_single_folder_scope(self, client, tmp_path):
        # Two bound folders; scanning one by folder_id catalogs only its files.
        a = tmp_path / "folderA"
        a.mkdir()
        _write_fits(a / "a_light.fits", imagetyp="LIGHT", filt="Ha", exptime=300.0)
        b = tmp_path / "folderB"
        b.mkdir()
        _write_fits(b / "b_light.fits", imagetyp="LIGHT", filt="Oiii", exptime=300.0)

        pid = await _make_project(client, "PerFolder")
        fa = (await client.post(f"/api/projects/{pid}/folders", json={"path": str(a)})).json()
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(b)})

        # Scan only folder A.
        run = (await client.post(f"/api/projects/{pid}/ingest?folder_id={fa['id']}")).json()
        assert run["status"] == "completed"
        assert run["subs_inserted"] == 1
        assert (await client.get(f"/api/projects/{pid}/catalog/summary")).json()["lights"] == 1

        # Scanning all folders now picks up B too (A re-scans idempotently).
        run2 = (await client.post(f"/api/projects/{pid}/ingest")).json()
        assert run2["subs_inserted"] == 1
        assert run2["subs_updated"] == 1
        assert (await client.get(f"/api/projects/{pid}/catalog/summary")).json()["lights"] == 2

    async def test_ingest_bad_folder_id_404(self, client, imaging_folder):
        pid = await _make_project(client, "BadFolder")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(imaging_folder)})
        r = await client.post(f"/api/projects/{pid}/ingest?folder_id=999999")
        assert r.status_code == 404

    async def test_remove_folder_purges_catalog(self, client, tmp_path):
        # Removing a folder drops its cataloged frames + emptied auto-sessions;
        # other folders' frames remain.
        a = tmp_path / "remA"
        a.mkdir()
        _write_fits(
            a / "a_light.fits",
            imagetyp="LIGHT",
            filt="Ha",
            exptime=300.0,
            extra={"DATE-OBS": "2026-03-15T23:30:00"},
        )
        b = tmp_path / "remB"
        b.mkdir()
        _write_fits(
            b / "b_light.fits",
            imagetyp="LIGHT",
            filt="Oiii",
            exptime=300.0,
            extra={"DATE-OBS": "2026-03-20T23:30:00"},
        )
        pid = await _make_project(client, "RemoveFolder")
        fa = (await client.post(f"/api/projects/{pid}/folders", json={"path": str(a)})).json()
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(b)})
        await client.post(f"/api/projects/{pid}/ingest")
        s = (await client.get(f"/api/projects/{pid}/catalog/summary")).json()
        assert s["lights"] == 2
        assert s["sessions"] == 2  # different nights

        r = await client.delete(f"/api/projects/{pid}/folders/{fa['id']}")
        assert r.status_code == 204
        s2 = (await client.get(f"/api/projects/{pid}/catalog/summary")).json()
        assert s2["lights"] == 1
        assert s2["sessions"] == 1  # A's session was emptied and dropped
        frames = (await client.get(f"/api/projects/{pid}/catalog/frames?frame_type=light")).json()[
            "rows"
        ]
        assert {f["filter_name"] for f in frames} == {"Oiii"}

    async def test_remove_folder_keeps_subs_with_other_location(self, client, tmp_path):
        # Same file under two folders dedupes to one sub with two file_locations.
        # Removing one folder drops only that location; the sub survives via the other.
        import shutil

        a = tmp_path / "dupA"
        a.mkdir()
        b = tmp_path / "dupB"
        b.mkdir()
        _write_fits(a / "light.fits", imagetyp="LIGHT", filt="Ha", exptime=300.0)
        shutil.copy(a / "light.fits", b / "light.fits")  # identical bytes → same hash

        pid = await _make_project(client, "DupFolder")
        fa = (await client.post(f"/api/projects/{pid}/folders", json={"path": str(a)})).json()
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(b)})
        await client.post(f"/api/projects/{pid}/ingest")
        assert (await client.get(f"/api/projects/{pid}/catalog/summary")).json()["lights"] == 1

        await client.delete(f"/api/projects/{pid}/folders/{fa['id']}")
        s = (await client.get(f"/api/projects/{pid}/catalog/summary")).json()
        assert s["lights"] == 1  # survives via folder B
        frames = (await client.get(f"/api/projects/{pid}/catalog/frames")).json()["rows"]
        assert frames[0]["path"].startswith(str(b))

    async def test_same_file_in_two_projects_creates_two_rows(self, client, tmp_path):
        # The same physical file cataloged into two DIFFERENT projects yields two
        # independent rows — each project owns its files, nothing is shared. Under
        # the old global model the second ingest silently reassigned the single
        # global row, so the first project would have shown 0 lights.
        import shutil

        a = tmp_path / "ownA"
        a.mkdir()
        b = tmp_path / "ownB"
        b.mkdir()
        _write_fits(a / "light.fits", imagetyp="LIGHT", filt="Ha", exptime=300.0)
        shutil.copy(a / "light.fits", b / "light.fits")  # identical bytes → same hash

        pid_a = await _make_project(client, "OwnA")
        pid_b = await _make_project(client, "OwnB")
        await client.post(f"/api/projects/{pid_a}/folders", json={"path": str(a)})
        await client.post(f"/api/projects/{pid_b}/folders", json={"path": str(b)})
        await client.post(f"/api/projects/{pid_a}/ingest")
        await client.post(f"/api/projects/{pid_b}/ingest")

        # Each project independently shows exactly one light.
        assert (await client.get(f"/api/projects/{pid_a}/catalog/summary")).json()["lights"] == 1
        assert (await client.get(f"/api/projects/{pid_b}/catalog/summary")).json()["lights"] == 1

        # Distinct rows, each owned by its project (different ids, paths under each folder).
        fa = (await client.get(f"/api/projects/{pid_a}/catalog/frames")).json()["rows"]
        fb = (await client.get(f"/api/projects/{pid_b}/catalog/frames")).json()["rows"]
        assert len(fa) == 1 and len(fb) == 1
        assert fa[0]["id"] != fb[0]["id"]
        assert fa[0]["path"].startswith(str(a))
        assert fb[0]["path"].startswith(str(b))

    async def test_lights_ingest_with_null_filter(self, client, imaging_folder):
        # Aliases are empty → filter_id stays NULL, but the raw FILTER is kept as
        # the hint and the light still catalogs as a light.
        pid = await _make_project(client, "PartialEq")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(imaging_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        frames = (await client.get(f"/api/projects/{pid}/catalog/frames")).json()
        lights = [f for f in frames["rows"] if f["frame_type"] == "light"]
        assert len(lights) == 2
        for light in lights:
            assert light["filter_name"] == "Ha"  # from filter_name_hint
            assert light["exposure_seconds"] == 300.0
            assert light["object_hint"] == "Tulip Nebula"

    async def test_catalog_frames_pagination(self, client, imaging_folder):
        pid = await _make_project(client, "Paginate")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(imaging_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        page = (await client.get(f"/api/projects/{pid}/catalog/frames?limit=2&offset=0")).json()
        # 4 sub frames (2 light + 1 dark + 1 flat; master is a processed_image).
        assert page["total"] == 4
        assert len(page["rows"]) == 2


# ── Thumbnails ───────────────────────────────────────────────────────────────


class TestThumbnailService:
    """Pure render path — exercised on a moderately large image (not 8x8) so the
    decimate-before-render path actually runs."""

    def test_mono_thumbnail(self, tmp_path: Path):
        from nightcrate.services.catalog_thumbnail import render_thumbnail_bytes

        path = tmp_path / "big_mono.fits"
        rng = np.random.default_rng(3)
        data = rng.integers(1400, 1600, size=(1200, 1600), dtype=np.uint16)
        data[500:700, 700:900] = 60000  # a bright blob to stretch
        fits.PrimaryHDU(data).writeto(path)

        png = render_thumbnail_bytes(str(path), max_px=96)
        assert png[:3] == b"\xff\xd8\xff"  # JPEG magic
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(png))
        assert max(img.size) <= 96
        assert img.mode in ("L", "RGB")

    def test_color_thumbnail(self, tmp_path: Path):
        from nightcrate.services.catalog_thumbnail import render_thumbnail_bytes

        path = tmp_path / "big_color.fits"
        rng = np.random.default_rng(4)
        data = rng.integers(1000, 2000, size=(3, 900, 1200), dtype=np.uint16)
        fits.PrimaryHDU(data).writeto(path)

        png = render_thumbnail_bytes(str(path), max_px=96)
        assert png[:3] == b"\xff\xd8\xff"

    def test_unreadable_raises(self, tmp_path: Path):
        from nightcrate.services.catalog_thumbnail import render_thumbnail_bytes

        bad = tmp_path / "broken.fits"
        bad.write_bytes(b"not fits")
        with pytest.raises(Exception):  # noqa: B017 - any load failure is fine; caller maps to 404
            render_thumbnail_bytes(str(bad))

    def test_render_never_uses_gpu_backend(self, tmp_path: Path, monkeypatch):
        """REGRESSION GUARD: the thumbnail path must never touch the mlx/GPU backend.

        mlx (Apple Metal) is not thread-safe; the catalog grid renders several
        thumbnails concurrently, and routing through the GPU stretch segfaults the
        process. Patch get_array_module to blow up if the thumbnail render reaches
        it (e.g. someone reintroduces imaging.stretch_plane / resolve_auto_stretch).
        """
        from nightcrate.services.catalog_thumbnail import render_thumbnail_bytes

        def _boom():
            raise AssertionError("thumbnail render must not use the GPU array module")

        monkeypatch.setattr("nightcrate.core.compute.get_array_module", _boom)
        monkeypatch.setattr("nightcrate.services.imaging.get_array_module", _boom)

        path = tmp_path / "guard.fits"
        rng = np.random.default_rng(11)
        data = rng.integers(1400, 1600, size=(600, 800), dtype=np.uint16)
        data[200:300, 300:400] = 60000
        fits.PrimaryHDU(data).writeto(path)

        png = render_thumbnail_bytes(str(path), max_px=96)
        assert png[:3] == b"\xff\xd8\xff"

    def test_concurrent_renders_complete(self, tmp_path: Path):
        """Many concurrent renders must all succeed (no native crash / corruption)."""
        from concurrent.futures import ThreadPoolExecutor

        from nightcrate.services.catalog_thumbnail import render_thumbnail_bytes

        paths = []
        for i in range(4):
            p = tmp_path / f"c{i}.fits"
            rng = np.random.default_rng(100 + i)
            d = rng.integers(1400, 1700, size=(800, 1000), dtype=np.uint16)
            d[300:500, 400:600] = 60000
            fits.PrimaryHDU(d).writeto(p)
            paths.append(str(p))

        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(render_thumbnail_bytes, paths * 6))
        assert all(r[:3] == b"\xff\xd8\xff" for r in results)
        assert len(results) == 24


class TestThumbnailEndpoint:
    async def test_thumbnail_served_and_cached(self, client, imaging_folder):
        pid = await _make_project(client, "Thumbs")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(imaging_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        frames = (await client.get(f"/api/projects/{pid}/catalog/frames")).json()
        frame_id = frames["rows"][0]["id"]

        r1 = await client.get(f"/api/projects/{pid}/catalog/frames/{frame_id}/thumbnail")
        assert r1.status_code == 200, r1.text
        assert r1.headers["content-type"] == "image/jpeg"
        assert r1.content[:3] == b"\xff\xd8\xff"

        # Second request is served from the on-disk cache (still 200, same bytes).
        r2 = await client.get(f"/api/projects/{pid}/catalog/frames/{frame_id}/thumbnail")
        assert r2.status_code == 200
        assert r2.content[:3] == b"\xff\xd8\xff"

    async def test_thumbnail_unknown_frame_404(self, client, imaging_folder):
        pid = await _make_project(client, "ThumbMiss")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(imaging_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        r = await client.get(f"/api/projects/{pid}/catalog/frames/999999/thumbnail")
        assert r.status_code == 404


# ── Classification refinements (dark-flats, filterless darks, grid filter) ────


@pytest.fixture
def calib_folder(tmp_path: Path) -> Path:
    """Mimics Fred's real data: lights @300s; flats auto-exposed @2.208s; dark-flats
    at the NOMINAL 2.2s (IMAGETYP=DARK, exposure NOT exactly equal to the flats — the
    case that broke exact matching); a real dark @300s with a stray FILTER; and a
    stacked master dark (IMAGETYP='Master Dark', NCOMBINE)."""
    folder = tmp_path / "Calib"
    folder.mkdir()
    _write_fits(folder / "light1.fits", imagetyp="LIGHT", filt="Ha", exptime=300.0)
    _write_fits(folder / "light2.fits", imagetyp="LIGHT", filt="Ha", exptime=300.0)
    _write_fits(folder / "flat1.fits", imagetyp="FLAT", filt="Ha", exptime=2.208)
    _write_fits(folder / "flat2.fits", imagetyp="FLAT", filt="Ha", exptime=2.208)
    # Dark-flats: IMAGETYP=DARK at the nominal 2.2s (flats are 2.208s — mismatched).
    _write_fits(folder / "df1.fits", imagetyp="DARK", exptime=2.2)
    _write_fits(folder / "df2.fits", imagetyp="DARK", exptime=2.2)
    # A real dark at the lights' 300 s exposure, carrying a stray FILTER.
    _write_fits(folder / "dark1.fits", imagetyp="DARK", filt="Ha", exptime=300.0)
    # A stacked master dark (processed_image, frame_type should parse to 'dark').
    _write_fits(
        folder / "MasterDark.fits",
        imagetyp="Master Dark",
        exptime=300.0,
        extra={"NCOMBINE": 20},
    )
    return folder


class TestClassificationRefinements:
    async def test_dark_flats_reclassified_by_exposure(self, client, calib_folder):
        pid = await _make_project(client, "Calib")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(calib_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        summary = (await client.get(f"/api/projects/{pid}/catalog/summary")).json()
        # Two 2 s darks → dark_flats; the 300 s dark stays a real dark.
        assert summary["dark_flats"] == 2
        assert summary["darks"] == 1
        assert summary["flats"] == 2
        assert summary["lights"] == 2

    async def test_darks_have_null_filter(self, client, calib_folder):
        pid = await _make_project(client, "CalibNull")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(calib_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        frames = (await client.get(f"/api/projects/{pid}/catalog/frames")).json()["rows"]
        # The real dark was written with FILTER=Ha but darks are filterless.
        darks = [f for f in frames if f["frame_type"] == "dark"]
        dark_flats = [f for f in frames if f["frame_type"] == "dark_flat"]
        assert darks and all(f["filter_name"] is None for f in darks)
        assert all(f["filter_name"] is None for f in dark_flats)
        # Lights keep their filter hint.
        lights = [f for f in frames if f["frame_type"] == "light"]
        assert all(f["filter_name"] == "Ha" for f in lights)

    async def test_frame_type_filter_param(self, client, calib_folder):
        pid = await _make_project(client, "CalibFilter")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(calib_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        page = (await client.get(f"/api/projects/{pid}/catalog/frames?frame_type=dark_flat")).json()
        assert page["total"] == 2
        assert {r["frame_type"] for r in page["rows"]} == {"dark_flat"}

        lights = (await client.get(f"/api/projects/{pid}/catalog/frames?frame_type=light")).json()
        assert lights["total"] == 2
        assert {r["frame_type"] for r in lights["rows"]} == {"light"}

    async def test_filter_name_scope_param(self, client, calib_folder):
        # The Lights/Flats filter pills scope the grid via ?filter_name=.
        pid = await _make_project(client, "CalibFilterName")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(calib_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        ha = (
            await client.get(f"/api/projects/{pid}/catalog/frames?frame_type=light&filter_name=Ha")
        ).json()
        assert ha["total"] == 2
        assert {r["filter_name"] for r in ha["rows"]} == {"Ha"}
        # A filter present nowhere in the project yields an empty, well-formed page.
        none = (
            await client.get(
                f"/api/projects/{pid}/catalog/frames?frame_type=light&filter_name=Oiii"
            )
        ).json()
        assert none["total"] == 0
        assert none["rows"] == []

    async def test_master_frame_type_parsed(self, client, calib_folder):
        pid = await _make_project(client, "Masters")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(calib_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        masters = (await client.get(f"/api/projects/{pid}/catalog/masters")).json()
        assert masters["total"] == 1
        m = masters["rows"][0]
        assert m["frame_type"] == "dark"  # parsed from "Master Dark"
        assert m["type_label"] == "Master: Dark"
        assert m["ncombine"] == 20

    async def test_flats_sorted_by_filter(self, client, tmp_path):
        # Flats sort by filter name even when the path would order them otherwise.
        folder = tmp_path / "Flats"
        folder.mkdir()
        # File names chosen so path order is Oiii-first; filter order must be Ha-first.
        _write_fits(folder / "a_flat.fits", imagetyp="FLAT", filt="Oiii", exptime=3.0)
        _write_fits(folder / "b_flat.fits", imagetyp="FLAT", filt="Ha", exptime=2.0)
        pid = await _make_project(client, "FlatSort")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        rows = (await client.get(f"/api/projects/{pid}/catalog/frames?frame_type=flat")).json()[
            "rows"
        ]
        assert [r["filter_name"] for r in rows] == ["Ha", "Oiii"]

    async def test_frame_dimensions_and_size(self, client, imaging_folder):
        # Catalog frames expose pixel dimensions + on-disk size for the cards.
        pid = await _make_project(client, "FrameMeta")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(imaging_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        rows = (await client.get(f"/api/projects/{pid}/catalog/frames?frame_type=light")).json()[
            "rows"
        ]
        assert rows
        for r in rows:
            assert r["image_width"] == 8  # synthetic 8x8 FITS
            assert r["image_height"] == 8
            assert r["file_size_bytes"] > 0

    async def test_master_filter_and_dimensions(self, client, tmp_path):
        # A master flat carries FILTER + NAXIS → Masters tab shows bandpass +
        # dimensions even without rig context (filter_id won't resolve).
        folder = tmp_path / "MMeta"
        folder.mkdir()
        _write_fits(
            folder / "masterFlat_Ha.fits",
            imagetyp="Master Flat",
            filt="Ha",
            exptime=2.2,
            extra={"NCOMBINE": 30},
        )
        pid = await _make_project(client, "MasterMeta")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        m = (await client.get(f"/api/projects/{pid}/catalog/masters")).json()["rows"][0]
        assert m["frame_type"] == "flat"
        assert m["filter_name"] == "Ha"  # from FILTER → line_name
        assert m["ncombine"] == 30
        assert m["dimensions"] == "8x8"  # from NAXIS1/NAXIS2
        assert m["total_exposure_seconds"] == 66.0  # EXPTIME 2.2 × NCOMBINE 30
        assert m["file_size_bytes"] > 0

    async def test_master_thumbnail(self, client, calib_folder):
        pid = await _make_project(client, "MasterThumb")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(calib_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        master_id = (await client.get(f"/api/projects/{pid}/catalog/masters")).json()["rows"][0][
            "id"
        ]
        r = await client.get(f"/api/projects/{pid}/catalog/masters/{master_id}/thumbnail")
        assert r.status_code == 200
        assert r.content[:3] == b"\xff\xd8\xff"

    async def test_filter_summary(self, client, calib_folder):
        pid = await _make_project(client, "FilterSummary")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(calib_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        stats = (
            await client.get(f"/api/projects/{pid}/catalog/filter-summary?frame_type=light")
        ).json()
        by_filter = {s["filter_name"]: s for s in stats}
        # calib_folder has 2 Ha lights @300s.
        assert by_filter["Ha"]["count"] == 2
        assert by_filter["Ha"]["total_seconds"] == 600.0
        # flats: 2 Ha @2.208s.
        fstats = (
            await client.get(f"/api/projects/{pid}/catalog/filter-summary?frame_type=flat")
        ).json()
        assert {s["filter_name"] for s in fstats} == {"Ha"}
        assert next(s for s in fstats if s["filter_name"] == "Ha")["count"] == 2

    async def test_filter_summary_rejects_bad_frame_type(self, client, calib_folder):
        pid = await _make_project(client, "FilterSummaryBad")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(calib_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        r = await client.get(f"/api/projects/{pid}/catalog/filter-summary?frame_type=dark")
        assert r.status_code == 422

    async def test_frames_page_timezone_defaults_utc(self, client, calib_folder):
        pid = await _make_project(client, "TzDefault")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(calib_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        page = (await client.get(f"/api/projects/{pid}/catalog/frames")).json()
        assert page["timezone"] == "UTC"  # no location set on the project

    async def test_others_lists_files(self, client, imaging_folder):
        # imaging_folder has a PHD2 log, a notes.md (other), and a .pxiproject.
        pid = await _make_project(client, "Others")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(imaging_folder)})
        await client.post(f"/api/projects/{pid}/ingest")
        others = (await client.get(f"/api/projects/{pid}/catalog/others")).json()
        labels = {r["type_label"] for r in others["rows"]}
        assert "Log" in labels
        assert "PixInsight Project" in labels
        assert "Other" in labels

    async def test_non_frame_counts_are_project_scoped(self, client, tmp_path):
        # file_location has no project FK; non-frame counts/listings must be scoped
        # to the project's source folders (path prefix), not workspace-wide.
        a = tmp_path / "projA"
        a.mkdir()
        _write_fits(a / "a_light.fits", imagetyp="LIGHT", filt="Ha")
        (a / "Autorun_Log_A.txt").write_text("log a\n")
        b = tmp_path / "projB"
        b.mkdir()
        _write_fits(b / "b_light.fits", imagetyp="LIGHT", filt="Oiii")
        (b / "Autorun_Log_B.txt").write_text("log b\n")
        (b / "Autorun_Log_B2.txt").write_text("log b2\n")

        pa = await _make_project(client, "ScopeA")
        await client.post(f"/api/projects/{pa}/folders", json={"path": str(a)})
        await client.post(f"/api/projects/{pa}/ingest")
        pb = await _make_project(client, "ScopeB")
        await client.post(f"/api/projects/{pb}/folders", json={"path": str(b)})
        await client.post(f"/api/projects/{pb}/ingest")

        sa = (await client.get(f"/api/projects/{pa}/catalog/summary")).json()
        sb = (await client.get(f"/api/projects/{pb}/catalog/summary")).json()
        assert sa["logs"] == 1  # only projA's log, not projB's two
        assert sb["logs"] == 2
        # Others listing is likewise scoped to each project's folder.
        oa = (await client.get(f"/api/projects/{pa}/catalog/others")).json()["rows"]
        assert all("/projA/" in r["path"] for r in oa if r["path"])
        assert all("/projB/" not in (r["path"] or "") for r in oa)
