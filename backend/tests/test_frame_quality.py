"""Frame quality metrics — the batch analyze pass (v0.41.3).

Covers the pure worker, the two endpoints, and the invariants that migration
0055 exists to protect.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.frame_quality import (
    ADU_FULL_SCALE,
    analyze_array,
    analyze_frame_file,
    wants_stars,
)
from nightcrate.services.pixel_loader import load_image

from .catalog_helpers import (
    _frames as _rows,
)
from .catalog_helpers import (
    _ingest_folder,
    _make_project,
    _seed_rig,
    _write_fits,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def quality_folder(tmp_path: Path) -> Path:
    """A capture folder with measurable lights plus one of each calibration type."""
    folder = tmp_path / "capture"
    folder.mkdir()
    _write_fits(folder / "light_a.fits", imagetyp="LIGHT", filt="Ha", stars=10)
    _write_fits(folder / "light_b.fits", imagetyp="LIGHT", filt="Ha", stars=15)
    _write_fits(folder / "light_c.fits", imagetyp="LIGHT", filt="Oiii", stars=5)
    _write_fits(folder / "dark_a.fits", imagetyp="DARK", filt=None, exptime=300.0)
    _write_fits(folder / "bias_a.fits", imagetyp="BIAS", filt=None, exptime=0.0)
    return folder


async def _analyze_all(client: AsyncClient, project_id: int, **scope) -> dict:
    """Fetch the pending ids and analyze them in one batch, as the UI does."""
    resp = await client.get(f"/api/projects/{project_id}/catalog/analyze/pending", params=scope)
    assert resp.status_code == 200, resp.text
    ids = resp.json()["frame_ids"]
    if not ids:
        return {"analyzed": 0, "no_stars": 0, "unreadable": 0, "skipped": 0, "errors": []}
    force = scope.get("force", False)
    resp = await client.post(
        f"/api/projects/{project_id}/catalog/analyze",
        json={"frame_ids": ids, "force": force},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize("frame_type", ["light", "flat"])
async def test_frame_list_filter_missing(client, tmp_path, frame_type):
    folder = tmp_path / f"{frame_type}-scope"
    folder.mkdir()
    image_type = frame_type.upper()
    for name in ("missing_a.fits", "missing_b.fits", "missing_c.fits"):
        _write_fits(folder / name, imagetyp=image_type, filt=None, stars=5)
    _write_fits(folder / "named.fits", imagetyp=image_type, filt="Ha", stars=5)

    other_folder = tmp_path / f"other-{frame_type}"
    other_folder.mkdir()
    _write_fits(other_folder / "missing_elsewhere.fits", imagetyp=image_type, filt=None, stars=5)
    project_id = await _make_project(client, f"Missing {frame_type}")
    other_project_id = await _make_project(client, f"Other missing {frame_type}")
    await _ingest_folder(client, project_id, folder)
    await _ingest_folder(client, other_project_id, other_folder)

    first = (
        await client.get(
            f"/api/projects/{project_id}/catalog/frames",
            params={"frame_type": frame_type, "filter_missing": True, "limit": 2},
        )
    ).json()
    second = (
        await client.get(
            f"/api/projects/{project_id}/catalog/frames",
            params={
                "frame_type": frame_type,
                "filter_missing": True,
                "limit": 2,
                "offset": 2,
            },
        )
    ).json()
    scoped_ids = [row["id"] for row in first["rows"] + second["rows"]]
    assert first["total"] == second["total"] == 3
    assert len(scoped_ids) == 3
    assert all(row["filter_name"] is None for row in first["rows"] + second["rows"])

    async with get_db() as conn:
        await conn.execute(
            "UPDATE sub_frame SET quality_analyzed_at = CURRENT_TIMESTAMP, quality_status = 'ok' "
            "WHERE id = ?",
            (scoped_ids[0],),
        )
        await conn.execute(
            "UPDATE sub_frame SET quality_analyzed_at = CURRENT_TIMESTAMP, "
            "quality_status = 'unreadable' WHERE id = ?",
            (scoped_ids[1],),
        )
        await conn.commit()

    scope = {"frame_type": frame_type, "filter_missing": True}
    pending = await client.get(f"/api/projects/{project_id}/catalog/analyze/pending", params=scope)
    forced = await client.get(
        f"/api/projects/{project_id}/catalog/analyze/pending",
        params={**scope, "force": True},
    )
    summary = await client.get(f"/api/projects/{project_id}/catalog/analyze/summary", params=scope)
    assert pending.json() == {"frame_ids": [scoped_ids[2]], "total": 3}
    assert set(forced.json()["frame_ids"]) == set(scoped_ids)
    assert forced.json()["total"] == 3
    assert summary.json() == {"total": 3, "analyzed": 2, "pending": 1, "unreadable": 1}


# ── the pure worker ───────────────────────────────────────────────────────────


class TestWorker:
    def test_star_metrics_on_a_light(self, tmp_path: Path):
        path = tmp_path / "light.fits"
        _write_fits(path, imagetyp="LIGHT", stars=10)

        out = analyze_frame_file(str(path), True)

        assert out["error"] is None
        assert out["status"] == "ok"
        # The fixture plants exactly 10 well-separated stars and detection
        # recovers all of them — a pinned count, not a range.
        assert out["star_count"] == 10
        assert out["hfr"] == pytest.approx(2.38, abs=0.05)
        assert out["snr_estimate"] > 100

    def test_background_matches_the_planted_level(self, tmp_path: Path):
        """The fixture's background is uniform 1400-1600, i.e. 1500 ADU."""
        path = tmp_path / "light.fits"
        _write_fits(path, imagetyp="LIGHT", stars=10)

        out = analyze_frame_file(str(path), True)

        assert out["background_adu"] == pytest.approx(1500, abs=25)
        assert out["median_adu"] == pytest.approx(1500, abs=25)

    def test_median_adu_is_hand_computable(self, tmp_path: Path):
        """A frame of a single known value reads back as exactly that value.

        Pins the un-normalization: normalize_to_01 divides uint16 by 65535, so
        multiplying back by ADU_FULL_SCALE must recover the original ADU.
        """
        path = tmp_path / "flat.fits"
        data = np.full((32, 32), 30000, dtype=np.uint16)
        hdu = fits.PrimaryHDU(data)
        hdu.header["IMAGETYP"] = "FLAT"
        hdu.header["DATE-OBS"] = "2026-03-15T23:30:00"
        hdu.writeto(path)

        out = analyze_frame_file(str(path), False)

        assert out["median_adu"] == pytest.approx(30000.0, abs=0.01)
        assert out["background_adu"] == pytest.approx(30000.0, abs=1.0)
        assert ADU_FULL_SCALE == 65535.0

    def test_uint16_result_is_frozen(self, tmp_path: Path):
        path = tmp_path / "frozen-flat.fits"
        fits.PrimaryHDU(np.full((32, 32), 30000, dtype=np.uint16)).writeto(path)

        image = load_image(str(path))
        assert analyze_array(image, False) == {
            "error": None,
            "status": "ok",
            "median_adu": 30000.0,
            "background_adu": 29999.999,
            "hfr": None,
            "star_count": None,
            "snr_estimate": None,
            "quality_units": "adu",
        }

    def test_negative_float_background_stays_in_recorded_units(self, tmp_path: Path):
        path = tmp_path / "negative-background.fits"
        fits.PrimaryHDU(np.full((32, 32), -0.25, dtype=np.float32)).writeto(path)

        out = analyze_frame_file(str(path), False)

        assert out["median_adu"] == pytest.approx(-0.25)
        assert out["background_adu"] == pytest.approx(-0.25, abs=1e-6)
        assert out["quality_units"] == "float"

    def test_without_stars_skips_detection(self, tmp_path: Path):
        path = tmp_path / "dark.fits"
        _write_fits(path, imagetyp="DARK", filt=None, stars=10)

        out = analyze_frame_file(str(path), False)

        assert out["status"] == "ok"
        assert out["median_adu"] is not None
        assert out["background_adu"] is not None
        assert out["hfr"] is None
        assert out["star_count"] is None
        assert out["snr_estimate"] is None

    def test_starless_light_is_no_stars_not_an_error(self, tmp_path: Path):
        """A frame with nothing detectable is a real result, not a failure."""
        path = tmp_path / "clouded.fits"
        _write_fits(path, imagetyp="LIGHT", stars=0)

        out = analyze_frame_file(str(path), True)

        assert out["error"] is None
        assert out["status"] == "no_stars"
        assert out["star_count"] == 0
        assert out["hfr"] is None

    def test_missing_file_returns_an_error_never_raises(self, tmp_path: Path):
        out = analyze_frame_file(str(tmp_path / "nope.fits"), True)

        assert out["error"]
        assert out["path"] == str(tmp_path / "nope.fits")

    def test_corrupt_file_returns_an_error_never_raises(self, tmp_path: Path):
        path = tmp_path / "junk.fits"
        path.write_bytes(b"this is not a FITS file")

        out = analyze_frame_file(str(path), True)

        assert out["error"]

    def test_wants_stars_is_lights_only(self):
        assert wants_stars("light") is True
        for ft in ("dark", "flat", "bias", "dark_flat", "unknown", None, ""):
            assert wants_stars(ft) is False

    def test_render_never_uses_gpu_backend(self, tmp_path: Path, monkeypatch):
        """mlx is not thread/process-safe on concurrent paths — the analyze pass
        must stay pure numpy. Patches both the definition site and the binding
        ``imaging`` imported, since a ``from ... import`` copies the reference."""

        def _boom():
            raise AssertionError("frame quality must not use the GPU array module")

        monkeypatch.setattr("nightcrate.core.compute.get_array_module", _boom)
        monkeypatch.setattr("nightcrate.services.imaging.get_array_module", _boom)

        path = tmp_path / "light.fits"
        _write_fits(path, imagetyp="LIGHT", stars=10)

        out = analyze_frame_file(str(path), True)

        assert out["error"] is None
        assert out["star_count"] == 10


# ── endpoints ─────────────────────────────────────────────────────────────────


class TestAnalyzeEndpoints:
    async def test_pending_then_analyze_fills_the_columns(
        self, client: AsyncClient, quality_folder: Path
    ):
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)

        result = await _analyze_all(client, pid, frame_type="light")

        assert result["analyzed"] == 3
        assert result["unreadable"] == 0
        rows = await _rows(client, pid, frame_type="light")
        assert len(rows) == 3
        for r in rows:
            assert r["quality_status"] == "ok"
            assert r["quality_analyzed_at"]
            assert r["quality_units"] == "adu"
            assert r["hfr"] is not None
            assert r["star_count"] is not None
            assert r["median_adu"] is not None

        async with get_db() as conn:
            stored = await (
                await conn.execute(
                    "SELECT DISTINCT quality_method FROM sub_frame "
                    "WHERE project_id = ? AND frame_type = 'light'",
                    (pid,),
                )
            ).fetchall()
        assert [row["quality_method"] for row in stored] == [2]

    async def test_calibration_frames_get_adu_only_and_leave_the_queue(
        self, client: AsyncClient, quality_folder: Path
    ):
        """The invariant migration 0055 exists for.

        A dark has no stars, so hfr stays NULL after a *successful* run. If
        "not analyzed" were keyed off hfr, every calibration frame would come
        back pending forever and the client's batch loop would never terminate.
        """
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)

        await _analyze_all(client, pid, frame_type="dark")

        rows = await _rows(client, pid, frame_type="dark")
        assert len(rows) == 1
        dark = rows[0]
        assert dark["quality_status"] == "ok"
        assert dark["quality_analyzed_at"]
        assert dark["median_adu"] is not None
        assert dark["background_adu"] is not None
        assert dark["hfr"] is None
        assert dark["star_count"] is None
        assert dark["snr_estimate"] is None

        # ...and it does not come back as pending.
        resp = await client.get(
            f"/api/projects/{pid}/catalog/analyze/pending", params={"frame_type": "dark"}
        )
        assert resp.json()["frame_ids"] == []
        assert resp.json()["total"] == 1

    async def test_re_analysis_is_idempotent_and_force_overrides(
        self, client: AsyncClient, quality_folder: Path
    ):
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)
        ids = (
            await client.get(
                f"/api/projects/{pid}/catalog/analyze/pending",
                params={"frame_type": "light"},
            )
        ).json()["frame_ids"]

        first = await client.post(f"/api/projects/{pid}/catalog/analyze", json={"frame_ids": ids})
        assert first.json()["analyzed"] == 3

        again = await client.post(f"/api/projects/{pid}/catalog/analyze", json={"frame_ids": ids})
        assert again.json() == {
            "analyzed": 0,
            "no_stars": 0,
            "unreadable": 0,
            "skipped": 3,
            "errors": [],
        }

        forced = await client.post(
            f"/api/projects/{pid}/catalog/analyze",
            json={"frame_ids": ids, "force": True},
        )
        assert forced.json()["analyzed"] == 3
        assert forced.json()["skipped"] == 0

    async def test_pending_honors_the_filter_pill(self, client: AsyncClient, quality_folder: Path):
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)

        resp = await client.get(
            f"/api/projects/{pid}/catalog/analyze/pending",
            params={"frame_type": "light", "filter_name": "Oiii"},
        )

        assert resp.status_code == 200
        assert len(resp.json()["frame_ids"]) == 1
        assert resp.json()["total"] == 1

    async def test_pending_force_includes_analyzed_frames(
        self, client: AsyncClient, quality_folder: Path
    ):
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)
        await _analyze_all(client, pid, frame_type="light")

        plain = await client.get(
            f"/api/projects/{pid}/catalog/analyze/pending", params={"frame_type": "light"}
        )
        forced = await client.get(
            f"/api/projects/{pid}/catalog/analyze/pending",
            params={"frame_type": "light", "force": True},
        )

        assert plain.json()["frame_ids"] == []
        assert len(forced.json()["frame_ids"]) == 3

    async def test_unreadable_file_is_recorded_and_not_retried(
        self, client: AsyncClient, quality_folder: Path
    ):
        """A file that vanishes after cataloging is reported once, not forever."""
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)
        (quality_folder / "light_a.fits").unlink()

        result = await _analyze_all(client, pid, frame_type="light")

        assert result["unreadable"] == 1
        assert result["analyzed"] == 2
        assert result["errors"]
        broken = [
            r
            for r in await _rows(client, pid, frame_type="light")
            if r["quality_status"] == "unreadable"
        ]
        assert len(broken) == 1
        assert broken[0]["quality_analyzed_at"]
        assert broken[0]["hfr"] is None

        # It left the queue — a re-run does not read it again.
        resp = await client.get(
            f"/api/projects/{pid}/catalog/analyze/pending", params={"frame_type": "light"}
        )
        assert resp.json()["frame_ids"] == []

    async def test_analyze_scopes_to_the_project(self, client: AsyncClient, quality_folder: Path):
        """Ids from another project are not analyzed just because they were sent."""
        pid = await _make_project(client, "Quality")
        other = await _make_project(client, "Other")
        await _ingest_folder(client, pid, quality_folder)
        ids = (
            await client.get(
                f"/api/projects/{pid}/catalog/analyze/pending",
                params={"frame_type": "light"},
            )
        ).json()["frame_ids"]

        resp = await client.post(f"/api/projects/{other}/catalog/analyze", json={"frame_ids": ids})

        assert resp.status_code == 200
        assert resp.json()["analyzed"] == 0

    async def test_unknown_project_404s(self, client: AsyncClient):
        resp = await client.post("/api/projects/999999/catalog/analyze", json={"frame_ids": [1]})
        assert resp.status_code == 404

    async def test_empty_batch_is_rejected(self, client: AsyncClient, quality_folder: Path):
        pid = await _make_project(client, "Quality")
        resp = await client.post(f"/api/projects/{pid}/catalog/analyze", json={"frame_ids": []})
        assert resp.status_code == 422

    async def test_concurrent_analyze_gets_409(
        self, client: AsyncClient, quality_folder: Path, monkeypatch
    ):
        """Single-flight: a second run while one is in flight is refused."""
        import nightcrate.api.ingest as ingest_api

        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)

        await ingest_api._ANALYZE_LOCK.acquire()
        try:
            resp = await client.post(
                f"/api/projects/{pid}/catalog/analyze", json={"frame_ids": [1]}
            )
        finally:
            ingest_api._ANALYZE_LOCK.release()

        assert resp.status_code == 409
        assert "already running" in resp.json()["detail"]


# ── sorting ───────────────────────────────────────────────────────────────────


class TestQualitySort:
    async def test_hfr_desc_puts_the_worst_frame_first(
        self, client: AsyncClient, quality_folder: Path
    ):
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)
        await _analyze_all(client, pid, frame_type="light")

        rows = await _rows(client, pid, frame_type="light", sort="hfr_desc")

        hfrs = [r["hfr"] for r in rows]
        assert hfrs == sorted(hfrs, reverse=True)

    async def test_stars_asc_puts_the_sparsest_frame_first(
        self, client: AsyncClient, quality_folder: Path
    ):
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)
        await _analyze_all(client, pid, frame_type="light")

        rows = await _rows(client, pid, frame_type="light", sort="stars_asc")

        # The fixture plants 10 / 15 / 5 stars across the three lights.
        assert [r["star_count"] for r in rows] == [5, 10, 15]

    async def test_unanalyzed_frames_sort_last_in_both_directions(
        self, client: AsyncClient, quality_folder: Path
    ):
        """Blanks sort last regardless of direction — the app-wide rule."""
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)
        ids = (
            await client.get(
                f"/api/projects/{pid}/catalog/analyze/pending",
                params={"frame_type": "light"},
            )
        ).json()["frame_ids"]
        # Analyze only one of the three lights.
        await client.post(f"/api/projects/{pid}/catalog/analyze", json={"frame_ids": ids[:1]})

        for order in ("hfr_desc", "hfr_asc"):
            rows = await _rows(client, pid, frame_type="light", sort=order)
            assert rows[0]["hfr"] is not None, order
            assert [r["hfr"] for r in rows[1:]] == [None, None], order

    async def test_unknown_sort_falls_back_and_does_not_500(
        self, client: AsyncClient, quality_folder: Path
    ):
        """The allow-list is the only thing that reaches an ORDER BY."""
        pid = await _make_project(client, "Quality")
        await _ingest_folder(client, pid, quality_folder)

        resp = await client.get(
            f"/api/projects/{pid}/catalog/frames",
            params={"frame_type": "light", "sort": "; DROP TABLE sub_frame"},
        )

        assert resp.status_code == 200
        assert len(resp.json()["rows"]) == 3
        # The table is still there.
        assert len(await _rows(client, pid, frame_type="light")) == 3


# ── catalog delete ────────────────────────────────────────────────────────────


class TestCatalogDelete:
    async def test_deletes_frames_and_their_file_locations(
        self, client: AsyncClient, quality_folder: Path
    ):
        pid = await _make_project(client, "Del")
        await _ingest_folder(client, pid, quality_folder)
        rows = await _rows(client, pid, frame_type="light")
        ids = [r["id"] for r in rows[:2]]

        resp = await client.post(f"/api/projects/{pid}/catalog/delete", json={"sub_frame_ids": ids})

        assert resp.status_code == 200, resp.text
        assert resp.json()["sub_frames"] == 2
        assert len(await _rows(client, pid, frame_type="light")) == 1
        sessions = (await client.get(f"/api/projects/{pid}/sessions")).json()
        assert len(sessions) == 1
        assert sessions[0]["num_subs"] == 1
        # The summary must move too, not just the list.
        summary = (await client.get(f"/api/projects/{pid}/catalog/summary")).json()
        assert summary["lights"] == 1

    async def test_deleting_last_file_location_drops_frame_and_refreshes_sessions(
        self, client: AsyncClient, quality_folder: Path
    ):
        pid = await _make_project(client, "Delete last location")
        await _ingest_folder(client, pid, quality_folder)
        frame = (await _rows(client, pid, frame_type="light"))[0]
        async with get_db() as conn:
            file_id = (
                await (
                    await conn.execute(
                        "SELECT id FROM file_location WHERE project_id = ? AND sub_frame_id = ?",
                        (pid, frame["id"]),
                    )
                ).fetchone()
            )["id"]

        response = await client.post(
            f"/api/projects/{pid}/catalog/delete", json={"file_ids": [file_id]}
        )

        assert response.status_code == 200, response.text
        assert response.json()["files"] == 1
        sessions = (await client.get(f"/api/projects/{pid}/sessions")).json()
        assert sum(row["num_subs"] for row in sessions) == 2

    async def test_delete_is_scoped_to_the_project(self, client: AsyncClient, quality_folder: Path):
        """An id from another project must not be deletable by sending it here."""
        pid = await _make_project(client, "Del")
        other = await _make_project(client, "Other")
        await _ingest_folder(client, pid, quality_folder)
        ids = [r["id"] for r in await _rows(client, pid, frame_type="light")]

        resp = await client.post(
            f"/api/projects/{other}/catalog/delete", json={"sub_frame_ids": ids}
        )

        assert resp.status_code == 200
        assert resp.json()["sub_frames"] == 0
        assert len(await _rows(client, pid, frame_type="light")) == 3

    async def test_a_rescan_brings_deleted_frames_back(
        self, client: AsyncClient, quality_folder: Path
    ):
        """Pins the documented behaviour of plain delete.

        The catalog is a view of what lies under the bound folders and nothing
        records the removal, so re-scanning re-catalogs the file. The UI warns
        before confirming; this test exists so the behaviour can't change by
        accident and go unnoticed.
        """
        pid = await _make_project(client, "Del")
        await _ingest_folder(client, pid, quality_folder)
        ids = [r["id"] for r in await _rows(client, pid, frame_type="light")]
        await client.post(f"/api/projects/{pid}/catalog/delete", json={"sub_frame_ids": ids})
        assert await _rows(client, pid, frame_type="light") == []

        await _ingest_folder(client, pid, quality_folder, add_folder=False)

        assert len(await _rows(client, pid, frame_type="light")) == 3

    async def test_empty_body_is_422(self, client: AsyncClient):
        pid = await _make_project(client, "Del")
        resp = await client.post(f"/api/projects/{pid}/catalog/delete", json={})
        assert resp.status_code == 422

    async def test_deleting_a_plain_file_leaves_frames_alone(
        self, client: AsyncClient, quality_folder: Path
    ):
        (quality_folder / "notes.md").write_text("some notes")
        pid = await _make_project(client, "Del")
        await _ingest_folder(client, pid, quality_folder)
        others = (await client.get(f"/api/projects/{pid}/catalog/others")).json()["rows"]
        note = next(o for o in others if o["kind"] == "file")

        resp = await client.post(
            f"/api/projects/{pid}/catalog/delete", json={"file_ids": [note["id"]]}
        )

        assert resp.json()["files"] == 1
        assert len(await _rows(client, pid, frame_type="light")) == 3


# ── generated sidecars ────────────────────────────────────────────────────────


class TestSidecarsAreNotCataloged:
    async def test_pixinsight_sidecars_are_skipped(self, client: AsyncClient, quality_folder: Path):
        """WBPP writes an .xnml and an .xdrz beside every registered sub.

        Cataloging them buries the real contents — a 600-sub project gains ~1,250
        rows nobody can act on — and they are regenerable outputs, not data.
        """
        (quality_folder / "light_a.xnml").write_text("<xnml/>")
        (quality_folder / "light_a.xdrz").write_text("<xdrz/>")
        (quality_folder / "proj.xpsm").write_text("<xpsm/>")
        # A log beside them must still be cataloged: "generated sidecar" is the
        # rule, not "not an image".
        (quality_folder / "PHD2_GuideLog_2026-01-01_200000.txt").write_text("phd2")

        pid = await _make_project(client, "Sidecars")
        await _ingest_folder(client, pid, quality_folder)

        others = (await client.get(f"/api/projects/{pid}/catalog/others")).json()["rows"]
        paths = [o["path"] or "" for o in others]
        assert not [p for p in paths if p.endswith((".xnml", ".xdrz", ".xpsm"))]
        assert [p for p in paths if p.endswith(".txt")], "logs must still be cataloged"

    def test_is_sidecar_vocabulary(self):
        from nightcrate.services.ingest_classify import is_sidecar

        for name in ("a.xnml", "A.XDRZ", "p.xpsm"):
            assert is_sidecar(name) is True, name
        for name in ("a.fits", "a.xisf", "log.txt", "p.pxiproject", "x.tif"):
            assert is_sidecar(name) is False, name


# ── HFR in arcseconds ─────────────────────────────────────────────────────────


class TestArcsecHfr:
    """The angular figure, derived on read from the rig the user tagged.

    ``_seed_rig`` builds a 3.76 um sensor at 600 mm, so the scale is
    ``206.265 * 3.76 / 600`` = 1.2926 arcsec/px — the same arithmetic as a real
    Askar V. Hand-computable, so these are pinned values rather than ranges.
    """

    EXPECTED_SCALE = pytest.approx(206.265 * 3.76 / 600, abs=1e-4)

    async def test_tagged_rig_yields_arcsec(self, client: AsyncClient, quality_folder: Path):
        rig = await _seed_rig("Arcsec Rig")
        pid = await _make_project(client, "Arcsec")
        resp = await client.post(
            f"/api/projects/{pid}/folders",
            json={"path": str(quality_folder), "rig_id": rig},
        )
        assert resp.status_code == 201, resp.text
        await _ingest_folder(client, pid, quality_folder, add_folder=False)
        await _analyze_all(client, pid, frame_type="light")

        row = (await _rows(client, pid, frame_type="light"))[0]

        assert row["pixel_scale_arcsec"] == self.EXPECTED_SCALE
        assert row["hfr"] is not None
        assert row["hfr_arcsec"] == pytest.approx(row["hfr"] * 206.265 * 3.76 / 600, abs=0.002)

    async def test_untagged_rig_leaves_it_null(self, client: AsyncClient, quality_folder: Path):
        """No rig means no honest scale — pixels, never a guessed conversion."""
        pid = await _make_project(client, "Arcsec")
        await _ingest_folder(client, pid, quality_folder)
        await _analyze_all(client, pid, frame_type="light")

        row = (await _rows(client, pid, frame_type="light"))[0]

        assert row["hfr"] is not None
        assert row["pixel_scale_arcsec"] is None
        assert row["hfr_arcsec"] is None

    async def test_binning_widens_the_scale(self, client: AsyncClient, tmp_path: Path):
        """A 2x2 binned frame has twice the effective pixel pitch."""
        folder = tmp_path / "binned"
        folder.mkdir()
        _write_fits(folder / "a.fits", imagetyp="LIGHT", stars=10)
        _write_fits(folder / "b.fits", imagetyp="LIGHT", stars=10)
        for f in ("a.fits", "b.fits"):
            with fits.open(folder / f, mode="update") as hdul:
                hdul[0].header["XBINNING"] = 2
                hdul[0].header["YBINNING"] = 2

        rig = await _seed_rig("Binned Rig")
        pid = await _make_project(client, "Binned")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(folder), "rig_id": rig})
        await _ingest_folder(client, pid, folder, add_folder=False)

        row = (await _rows(client, pid, frame_type="light"))[0]

        assert row["binning"] == "2x2"
        assert row["pixel_scale_arcsec"] == pytest.approx(2 * 206.265 * 3.76 / 600, abs=1e-4)

    async def test_arcsec_sort_orders_across_rigs(self, client: AsyncClient, tmp_path: Path):
        """The point of the arcsec sort: pixels rank by focal length, not seeing."""
        pid = await _make_project(client, "TwoRigs")
        short = await _seed_rig("Short FL")
        long_fl = await _seed_rig("Long FL")
        # Give the second rig 4x the focal length, so its pixels are 4x finer.
        async with __import__("nightcrate.db.session", fromlist=["get_db"]).get_db() as conn:
            await conn.execute(
                "UPDATE telescope_configuration SET effective_focal_length_mm = 2400 "
                "WHERE id = (SELECT telescope_configuration_id FROM rig WHERE id = ?)",
                (long_fl,),
            )
            await conn.commit()

        for name, rig in (("wide", short), ("narrow", long_fl)):
            folder = tmp_path / name
            folder.mkdir()
            _write_fits(folder / "a.fits", imagetyp="LIGHT", stars=10)
            _write_fits(folder / "b.fits", imagetyp="LIGHT", stars=10)
            await client.post(
                f"/api/projects/{pid}/folders", json={"path": str(folder), "rig_id": rig}
            )
        await _ingest_folder(client, pid, tmp_path / "wide", add_folder=False)
        await _analyze_all(client, pid, frame_type="light")

        rows = await _rows(client, pid, frame_type="light", sort="hfr_arcsec_desc")
        arcsecs = [r["hfr_arcsec"] for r in rows if r["hfr_arcsec"] is not None]

        assert arcsecs == sorted(arcsecs, reverse=True)
        # Same measured pixels, different optics -> different angular size.
        assert len({round(a, 2) for a in arcsecs}) > 1
