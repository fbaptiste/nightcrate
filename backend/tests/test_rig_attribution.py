"""Tests for rig attribution + equipment re-resolution (v0.41.0).

Three layers:
  * Pure ``match_rig`` elimination logic — no DB.
  * End-to-end ingest → attribution flow against synthetic FITS folders,
    including the two-camera-same-model disambiguation and session re-keying.
  * The v0.41.0 endpoints: unresolved-alias review (list/confirm/dismiss),
    per-frame equipment override (user-source protection), and re-run.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.equipment_resolver import _LINE_NAME_MAP
from nightcrate.services.rig_attribution import RigCandidate, load_project_rigs, match_rig

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Pure: match_rig elimination logic ────────────────────────────────────────


def _cand(
    rig_id: int,
    *,
    camera_id: int = 1,
    camera_twin: tuple[int, int] = (1, 1),  # (manufacturer_id, sensor_id)
    focal: float = 2800.0,
    filter_ids: set[int] | None = None,
    line_names: set[str] | None = None,
) -> RigCandidate:
    return RigCandidate(
        rig_id=rig_id,
        camera_id=camera_id,
        camera_twin_key=camera_twin,
        focal_length_mm=focal,
        filter_ids=filter_ids or set(),
        line_names=line_names or set(),
    )


class TestMatchRig:
    def test_no_candidates_returns_none(self):
        assert (
            match_rig(
                [],
                camera_id=1,
                camera_twin_key=(1, 1),
                focal_length_mm=None,
                line_name=None,
                filter_id=None,
            )
            is None
        )

    def test_single_rig_no_signals_attributes(self):
        # Assigning one rig to the project means "this project used this rig";
        # a signal-free frame has nothing contradicting it.
        cand = match_rig(
            [_cand(1)],
            camera_id=None,
            camera_twin_key=None,
            focal_length_mm=None,
            line_name=None,
            filter_id=None,
        )
        assert cand is not None and cand.rig_id == 1

    def test_single_rig_contradicted_by_focal_returns_none(self):
        cand = match_rig(
            [_cand(1, focal=2800.0)],
            camera_id=None,
            camera_twin_key=None,
            focal_length_mm=600.0,
            line_name=None,
            filter_id=None,
        )
        assert cand is None

    def test_two_rigs_focal_discriminates(self):
        rigs = [_cand(1, focal=2800.0), _cand(2, focal=600.0)]
        cand = match_rig(
            rigs,
            camera_id=None,
            camera_twin_key=None,
            focal_length_mm=605.0,
            line_name=None,
            filter_id=None,
        )
        assert cand is not None and cand.rig_id == 2

    def test_focal_tolerance_boundary(self):
        rigs = [_cand(1, focal=600.0)]
        inside = match_rig(
            rigs,
            camera_id=None,
            camera_twin_key=None,
            focal_length_mm=629.9,  # +4.98 % of 600 — inside the ±5 % band
            line_name=None,
            filter_id=None,
        )
        outside = match_rig(
            rigs,
            camera_id=None,
            camera_twin_key=None,
            focal_length_mm=640.0,  # +6.7 % — outside
            line_name=None,
            filter_id=None,
        )
        assert inside is not None and outside is None

    def test_two_rigs_camera_discriminates(self):
        rigs = [
            _cand(1, camera_id=10, camera_twin=(1, 10)),
            _cand(2, camera_id=20, camera_twin=(1, 20)),
        ]
        cand = match_rig(
            rigs,
            camera_id=20,
            camera_twin_key=(1, 20),
            focal_length_mm=None,
            line_name=None,
            filter_id=None,
        )
        assert cand is not None and cand.rig_id == 2

    def test_same_model_twin_does_not_eliminate(self):
        # The §7 two-camera problem: both rigs carry an ASI 2600MM Pro body; the
        # alias resolves the shared INSTRUME to body 10. Focal length must still
        # be able to pick rig 2 (body 20) — same-model is consistent, not a
        # contradiction.
        rigs = [
            _cand(1, camera_id=10, focal=2800.0),
            _cand(2, camera_id=20, focal=600.0),
        ]
        cand = match_rig(
            rigs,
            camera_id=10,
            camera_twin_key=(1, 1),
            focal_length_mm=600.0,
            line_name=None,
            filter_id=None,
        )
        assert cand is not None and cand.rig_id == 2

    def test_two_identical_rigs_no_discriminator_returns_none(self):
        rigs = [_cand(1, camera_id=10), _cand(2, camera_id=20)]
        cand = match_rig(
            rigs,
            camera_id=10,
            camera_twin_key=(1, 1),
            focal_length_mm=2800.0,
            line_name=None,
            filter_id=None,
        )
        assert cand is None  # both survive → ambiguous → never guess

    def test_filter_line_discriminates(self):
        rigs = [
            _cand(1, line_names={"Ha", "Oiii", "Sii"}, filter_ids={7, 8, 9}),
            _cand(2, line_names={"Lum", "R", "G", "B"}, filter_ids={11, 12, 13, 14}),
        ]
        cand = match_rig(
            rigs,
            camera_id=None,
            camera_twin_key=None,
            focal_length_mm=None,
            line_name="Ha",
            filter_id=None,
        )
        assert cand is not None and cand.rig_id == 1

    def test_user_filter_id_takes_precedence_over_line(self):
        rigs = [
            _cand(1, line_names={"Ha"}, filter_ids={7}),
            _cand(2, line_names={"Ha"}, filter_ids={8}),
        ]
        cand = match_rig(
            rigs,
            camera_id=None,
            camera_twin_key=None,
            focal_length_mm=None,
            line_name="Ha",
            filter_id=8,
        )
        assert cand is not None and cand.rig_id == 2

    def test_rig_without_slots_filter_neutral(self):
        rigs = [_cand(1, filter_ids=set(), line_names=set())]
        cand = match_rig(
            rigs,
            camera_id=None,
            camera_twin_key=None,
            focal_length_mm=None,
            line_name="Ha",
            filter_id=None,
        )
        assert cand is not None and cand.rig_id == 1


# ── Equipment / rig seeding helpers (direct SQL — API setup would drag in the
#    whole equipment-form surface these tests don't exercise) ─────────────────


async def _seed_equipment(two_rigs: bool = False) -> dict:
    """Seed manufacturer/sensor/cameras/telescopes/configs/filters/rigs.

    Rig 1 ("C11 Rig"): camera A, 2800 mm, Optolong Ha 7nm loaded.
    Rig 2 ("Askar Rig", when two_rigs): camera B (same model string), 600 mm,
    Antlia Ha 3nm loaded.
    """
    ids: dict = {}
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")

        async def insert(sql: str, params: tuple) -> int:
            cursor = await conn.execute(sql, params)
            return cursor.lastrowid

        mfr = await insert("INSERT INTO manufacturer (name) VALUES (?)", ("TestMfg",))
        sensor = await insert(
            "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, "
            "pixel_size_um, resolution_x, resolution_y) VALUES (?, 'IMX571', 'mono', "
            "3.76, 6248, 4176)",
            (mfr,),
        )
        ids["camera_a"] = await insert(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name) "
            "VALUES (?, ?, 'ASI2600MM Pro')",
            (mfr, sensor),
        )
        scope_a = await insert(
            "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) "
            "VALUES (?, 'C11', 280)",
            (mfr,),
        )
        config_a = await insert(
            "INSERT INTO telescope_configuration (telescope_id, config_name, "
            "effective_focal_length_mm, effective_focal_ratio, is_native) "
            "VALUES (?, 'Native', 2800, 10.0, 1)",
            (scope_a,),
        )
        # lastrowid is stale when OR IGNORE ignores → always SELECT the id.
        await conn.execute(
            "INSERT OR IGNORE INTO filter_type (name, description, source) "
            "VALUES ('narrowband_single', 'test', 'seed')"
        )
        cursor = await conn.execute("SELECT id FROM filter_type WHERE name = 'narrowband_single'")
        ftype = (await cursor.fetchone())["id"]
        ids["filter_optolong_ha"] = await insert(
            "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) "
            "VALUES (?, ?, 'Optolong Ha 7nm')",
            (mfr, ftype),
        )
        await conn.execute(
            "INSERT INTO filter_passband (filter_id, line_name, central_wavelength_nm, "
            "bandwidth_nm) VALUES (?, 'Ha', 656.3, 7)",
            (ids["filter_optolong_ha"],),
        )
        ids["rig_1"] = await insert(
            "INSERT INTO rig (name, telescope_configuration_id, camera_id) "
            "VALUES ('C11 Rig', ?, ?)",
            (config_a, ids["camera_a"]),
        )
        await conn.execute(
            "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 1, ?)",
            (ids["rig_1"], ids["filter_optolong_ha"]),
        )

        # Alias: the shared INSTRUME string maps to camera A (one body).
        await conn.execute(
            "INSERT INTO camera_alias (camera_id, alias, source, confirmed) "
            "VALUES (?, 'zwo asi2600mm pro', 'user', 1)",
            (ids["camera_a"],),
        )

        if two_rigs:
            # Second physical body of the same model: camera has
            # UNIQUE(manufacturer_id, model_name), so twins carry distinct row
            # names but share manufacturer + sensor (the twin key).
            ids["camera_b"] = await insert(
                "INSERT INTO camera (manufacturer_id, sensor_id, model_name) "
                "VALUES (?, ?, 'ASI2600MM Pro (Askar)')",
                (mfr, sensor),
            )
            scope_b = await insert(
                "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) "
                "VALUES (?, 'Askar V', 80)",
                (mfr,),
            )
            config_b = await insert(
                "INSERT INTO telescope_configuration (telescope_id, config_name, "
                "effective_focal_length_mm, effective_focal_ratio, is_native) "
                "VALUES (?, 'Reduced', 600, 7.5, 1)",
                (scope_b,),
            )
            ids["filter_antlia_ha"] = await insert(
                "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) "
                "VALUES (?, ?, 'Antlia Ha 3nm')",
                (mfr, ftype),
            )
            await conn.execute(
                "INSERT INTO filter_passband (filter_id, line_name, "
                "central_wavelength_nm, bandwidth_nm) VALUES (?, 'Ha', 656.3, 3)",
                (ids["filter_antlia_ha"],),
            )
            ids["rig_2"] = await insert(
                "INSERT INTO rig (name, telescope_configuration_id, camera_id) "
                "VALUES ('Askar Rig', ?, ?)",
                (config_b, ids["camera_b"]),
            )
            await conn.execute(
                "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 1, ?)",
                (ids["rig_2"], ids["filter_antlia_ha"]),
            )
        await conn.commit()
    return ids


async def _assign_rigs(client: AsyncClient, project_id: int, rig_ids: list[int]) -> None:
    resp = await client.put(f"/api/projects/{project_id}/rigs", json={"rig_ids": rig_ids})
    assert resp.status_code == 200, resp.text


async def _make_project(client: AsyncClient, name: str) -> int:
    resp = await client.post("/api/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


_PIXEL_SEED = itertools.count(1000)


def _write_fits(
    path: Path,
    *,
    imagetyp: str = "LIGHT",
    filt: str | None = "Ha",
    focallen: float | None = 2800.0,
    instrume: str = "ZWO ASI2600MM Pro",
    exptime: float = 300.0,
    date_obs: str = "2026-03-15T23:30:00",
) -> None:
    data = np.full((8, 8), next(_PIXEL_SEED) % 65535, dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    hdu.header["IMAGETYP"] = imagetyp
    hdu.header["EXPTIME"] = exptime
    hdu.header["INSTRUME"] = instrume
    hdu.header["DATE-OBS"] = date_obs
    if filt is not None:
        hdu.header["FILTER"] = filt
    if focallen is not None:
        hdu.header["FOCALLEN"] = focallen
    hdu.writeto(path, overwrite=True)


async def _ingest_folder(client: AsyncClient, project_id: int, folder: Path) -> dict:
    resp = await client.post(f"/api/projects/{project_id}/folders", json={"path": str(folder)})
    assert resp.status_code == 201, resp.text
    resp = await client.post(f"/api/projects/{project_id}/ingest")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _frames(client: AsyncClient, project_id: int, **params) -> list[dict]:
    resp = await client.get(f"/api/projects/{project_id}/catalog/frames", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["rows"]


# ── End-to-end: ingest attributes rigs + back-fills filters ─────────────────


class TestAttributionEndToEnd:
    async def test_single_rig_project_attributes_and_backfills(self, client, tmp_path):
        ids = await _seed_equipment()
        pid = await _make_project(client, "SingleRig")
        await _assign_rigs(client, pid, [ids["rig_1"]])

        folder = tmp_path / "capture"
        folder.mkdir()
        _write_fits(folder / "light_001.fits")
        _write_fits(folder / "light_002.fits")
        await _ingest_folder(client, pid, folder)

        rows = await _frames(client, pid, frame_type="light")
        assert len(rows) == 2
        for row in rows:
            assert row["rig_id"] == ids["rig_1"]
            assert row["rig_name"] == "C11 Rig"
            assert row["camera_id"] == ids["camera_a"]
            # Filter back-filled through the rig's loadout ("Ha" → Optolong Ha 7nm).
            assert row["filter_id"] == ids["filter_optolong_ha"]
            assert row["filter_model"] == "Optolong Ha 7nm"
            assert row["rig_source"] == "auto"

        # Sessions are keyed to the attributed rig.
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT DISTINCT s.rig_id FROM session s "
                "JOIN sub_frame sf ON sf.session_id = s.id WHERE s.project_id = ?",
                (pid,),
            )
            rig_ids = [r["rig_id"] for r in await cursor.fetchall()]
        assert rig_ids == [ids["rig_1"]]

    async def test_no_project_rigs_no_discovery(self, client, tmp_path):
        await _seed_equipment()
        pid = await _make_project(client, "NoRigs")

        folder = tmp_path / "capture"
        folder.mkdir()
        _write_fits(folder / "light_001.fits")
        await _ingest_folder(client, pid, folder)

        rows = await _frames(client, pid, frame_type="light")
        assert rows[0]["rig_id"] is None
        # Camera still resolves by alias, but the filter can't (no rig scope).
        assert rows[0]["camera_id"] is not None
        assert rows[0]["filter_id"] is None
        assert rows[0]["filter_name"] == "Ha"  # hint preserved

    async def test_two_camera_disambiguation_by_focal_length(self, client, tmp_path):
        # Both bodies write INSTRUME='ZWO ASI2600MM Pro'; the alias maps to
        # camera A. FOCALLEN=600 must attribute rig 2 AND correct the camera to
        # body B — the §7 disambiguation this version exists for.
        ids = await _seed_equipment(two_rigs=True)
        pid = await _make_project(client, "DualRig")
        await _assign_rigs(client, pid, [ids["rig_1"], ids["rig_2"]])

        folder = tmp_path / "capture"
        folder.mkdir()
        _write_fits(folder / "c11_001.fits", focallen=2800.0)
        _write_fits(folder / "askar_001.fits", focallen=600.0)
        await _ingest_folder(client, pid, folder)

        rows = {r["path"].split("/")[-1]: r for r in await _frames(client, pid)}
        c11 = rows["c11_001.fits"]
        askar = rows["askar_001.fits"]
        assert c11["rig_id"] == ids["rig_1"]
        assert c11["camera_id"] == ids["camera_a"]
        assert c11["filter_id"] == ids["filter_optolong_ha"]
        assert askar["rig_id"] == ids["rig_2"]
        assert askar["camera_id"] == ids["camera_b"]  # rig-corrected body
        assert askar["filter_id"] == ids["filter_antlia_ha"]

        # Dual-rig same night → two sessions, one per rig.
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(DISTINCT s.id) AS n FROM session s "
                "JOIN sub_frame sf ON sf.session_id = s.id WHERE s.project_id = ?",
                (pid,),
            )
            assert (await cursor.fetchone())["n"] == 2

    async def test_no_focal_signal_two_rigs_stays_unattributed(self, client, tmp_path):
        ids = await _seed_equipment(two_rigs=True)
        pid = await _make_project(client, "AmbiguousRig")
        await _assign_rigs(client, pid, [ids["rig_1"], ids["rig_2"]])

        folder = tmp_path / "capture"
        folder.mkdir()
        # No FOCALLEN; filter 'Ha' is loaded on both rigs → both survive.
        _write_fits(folder / "light_001.fits", focallen=None)
        await _ingest_folder(client, pid, folder)

        rows = await _frames(client, pid)
        assert rows[0]["rig_id"] is None  # never guess

    async def test_rerun_is_idempotent(self, client, tmp_path):
        ids = await _seed_equipment()
        pid = await _make_project(client, "Idempotent")
        await _assign_rigs(client, pid, [ids["rig_1"]])

        folder = tmp_path / "capture"
        folder.mkdir()
        _write_fits(folder / "light_001.fits")
        await _ingest_folder(client, pid, folder)

        r1 = await client.post(f"/api/projects/{pid}/resolution/rerun")
        assert r1.status_code == 200, r1.text
        r2 = await client.post(f"/api/projects/{pid}/resolution/rerun")
        assert r2.json()["frames_changed"] == 0
        assert r2.json()["rigs_attributed"] == r1.json()["rigs_attributed"]


# ── Unresolved-alias review endpoints ─────────────────────────────────────────


class TestUnresolvedReview:
    async def test_ingest_populates_queue_and_confirm_promotes(self, client, tmp_path):
        ids = await _seed_equipment()
        pid = await _make_project(client, "AliasFlow")
        await _assign_rigs(client, pid, [ids["rig_1"]])

        folder = tmp_path / "capture"
        folder.mkdir()
        # Unknown INSTRUME → camera lands in the unresolved queue.
        _write_fits(folder / "light_001.fits", instrume="MysteryCam 9000")
        await _ingest_folder(client, pid, folder)

        listing = (await client.get("/api/equipment/unresolved")).json()
        cams = [i for i in listing["items"] if i["equipment_kind"] == "camera"]
        assert any(i["normalized_alias"] == "mysterycam 9000" for i in cams)
        assert listing["pending_by_kind"].get("camera", 0) >= 1
        obs = next(i for i in cams if i["normalized_alias"] == "mysterycam 9000")

        # Frame is camera-less before confirmation.
        rows = await _frames(client, pid)
        assert rows[0]["camera_id"] is None

        # Confirm → alias inserted; re-run picks it up.
        resp = await client.post(
            f"/api/equipment/unresolved/{obs['id']}/confirm",
            json={"equipment_id": ids["camera_a"]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["observation"]["resolved_at"] is not None

        await client.post(f"/api/projects/{pid}/resolution/rerun")
        rows = await _frames(client, pid)
        assert rows[0]["camera_id"] == ids["camera_a"]

        # The observation left the pending list.
        listing = (await client.get("/api/equipment/unresolved")).json()
        assert all(i["id"] != obs["id"] for i in listing["items"])

    async def test_confirm_already_resolved_409(self, client, tmp_path):
        ids = await _seed_equipment()
        pid = await _make_project(client, "AliasTwice")
        folder = tmp_path / "capture"
        folder.mkdir()
        _write_fits(folder / "light_001.fits", instrume="TwiceCam")
        await _ingest_folder(client, pid, folder)

        listing = (await client.get("/api/equipment/unresolved")).json()
        obs = next(i for i in listing["items"] if i["normalized_alias"] == "twicecam")
        first = await client.post(
            f"/api/equipment/unresolved/{obs['id']}/confirm",
            json={"equipment_id": ids["camera_a"]},
        )
        assert first.status_code == 200
        second = await client.post(
            f"/api/equipment/unresolved/{obs['id']}/confirm",
            json={"equipment_id": ids["camera_a"]},
        )
        assert second.status_code == 409

    async def test_confirm_unknown_equipment_404(self, client, tmp_path):
        await _seed_equipment()
        pid = await _make_project(client, "AliasBadEq")
        folder = tmp_path / "capture"
        folder.mkdir()
        _write_fits(folder / "light_001.fits", instrume="GhostCam")
        await _ingest_folder(client, pid, folder)

        listing = (await client.get("/api/equipment/unresolved")).json()
        obs = next(i for i in listing["items"] if i["normalized_alias"] == "ghostcam")
        resp = await client.post(
            f"/api/equipment/unresolved/{obs['id']}/confirm",
            json={"equipment_id": 999999},
        )
        assert resp.status_code == 404

    async def test_dismiss_removes_observation(self, client, tmp_path):
        await _seed_equipment()
        pid = await _make_project(client, "AliasDismiss")
        folder = tmp_path / "capture"
        folder.mkdir()
        _write_fits(folder / "light_001.fits", instrume="DismissMe")
        await _ingest_folder(client, pid, folder)

        listing = (await client.get("/api/equipment/unresolved")).json()
        obs = next(i for i in listing["items"] if i["normalized_alias"] == "dismissme")
        resp = await client.delete(f"/api/equipment/unresolved/{obs['id']}")
        assert resp.status_code == 204
        listing = (await client.get("/api/equipment/unresolved")).json()
        assert all(i["id"] != obs["id"] for i in listing["items"])


# ── Per-frame equipment override ──────────────────────────────────────────────


class TestEquipmentOverride:
    async def _setup(self, client, tmp_path, *, two_rigs: bool = False):
        ids = await _seed_equipment(two_rigs=two_rigs)
        pid = await _make_project(client, f"Override-{next(_PIXEL_SEED)}")
        await _assign_rigs(client, pid, [ids["rig_1"]])
        folder = tmp_path / "capture"
        folder.mkdir()
        _write_fits(folder / "light_001.fits")
        _write_fits(folder / "dark_001.fits", imagetyp="DARK", filt=None)
        await _ingest_folder(client, pid, folder)
        return ids, pid

    async def test_override_survives_rerun_and_rescan(self, client, tmp_path):
        ids, pid = await self._setup(client, tmp_path, two_rigs=True)
        light = (await _frames(client, pid, frame_type="light"))[0]

        # Override the rig to rig 2 (not even assigned to the project — user is
        # the authority) — and the filter to the Antlia.
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/equipment",
            json={"rig_id": ids["rig_2"], "filter_id": ids["filter_antlia_ha"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rig_id"] == ids["rig_2"]
        assert body["rig_source"] == "user"
        assert body["filter_id"] == ids["filter_antlia_ha"]
        assert body["filter_source"] == "user"

        # Re-run must not clobber the overrides.
        await client.post(f"/api/projects/{pid}/resolution/rerun")
        light = (await _frames(client, pid, frame_type="light"))[0]
        assert light["rig_id"] == ids["rig_2"]
        assert light["filter_id"] == ids["filter_antlia_ha"]

        # A full re-scan must not either.
        await client.post(f"/api/projects/{pid}/ingest")
        light = (await _frames(client, pid, frame_type="light"))[0]
        assert light["rig_id"] == ids["rig_2"]
        assert light["filter_id"] == ids["filter_antlia_ha"]

    async def test_reset_to_auto_lets_rerun_refill(self, client, tmp_path):
        ids, pid = await self._setup(client, tmp_path)
        light = (await _frames(client, pid, frame_type="light"))[0]

        await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/equipment",
            json={"rig_id": None},
        )
        light = (await _frames(client, pid, frame_type="light"))[0]
        assert light["rig_id"] is None and light["rig_source"] == "user"

        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/equipment",
            json={"reset_to_auto": ["rig_id"]},
        )
        assert resp.json()["rig_source"] == "auto"
        await client.post(f"/api/projects/{pid}/resolution/rerun")
        light = (await _frames(client, pid, frame_type="light"))[0]
        assert light["rig_id"] == ids["rig_1"]

    async def test_override_rig_rekeys_session(self, client, tmp_path):
        ids, pid = await self._setup(client, tmp_path, two_rigs=True)
        light = (await _frames(client, pid, frame_type="light"))[0]
        await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/equipment",
            json={"rig_id": ids["rig_2"]},
        )
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT s.rig_id FROM session s JOIN sub_frame sf ON sf.session_id = s.id "
                "WHERE sf.id = ?",
                (light["id"],),
            )
            assert (await cursor.fetchone())["rig_id"] == ids["rig_2"]

    async def test_filter_on_dark_422(self, client, tmp_path):
        ids, pid = await self._setup(client, tmp_path)
        dark = (await _frames(client, pid, frame_type="dark"))[0]
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{dark['id']}/equipment",
            json={"filter_id": ids["filter_optolong_ha"]},
        )
        assert resp.status_code == 422

    async def test_unknown_rig_404_and_empty_body_422(self, client, tmp_path):
        _, pid = await self._setup(client, tmp_path)
        light = (await _frames(client, pid, frame_type="light"))[0]
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/equipment",
            json={"rig_id": 999999},
        )
        assert resp.status_code == 404
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{light['id']}/equipment", json={}
        )
        assert resp.status_code == 422

    async def test_override_unknown_frame_404(self, client, tmp_path):
        _, pid = await self._setup(client, tmp_path)
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/999999/equipment",
            json={"rig_id": None},
        )
        assert resp.status_code == 404


# ── v0.41.0 code-review fixes ────────────────────────────────────────────────


class TestSingleFilterRig:
    """A rig may carry one fixed filter instead of a wheel (rig.single_filter_id).

    Loading the loadout only from rig_filter_slot left such a rig with an empty
    filter set, so the filter signal could never eliminate it.
    """

    async def test_load_project_rigs_includes_single_filter(self, client):
        ids = await _seed_equipment()
        pid = await _make_project(client, "SingleFilterRig")

        async with get_db() as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            # Rebuild rig_1 as a wheel-less rig carrying one fixed filter.
            await conn.execute("DELETE FROM rig_filter_slot WHERE rig_id = ?", (ids["rig_1"],))
            await conn.execute(
                "UPDATE rig SET filter_wheel_id = NULL, single_filter_id = ? WHERE id = ?",
                (ids["filter_optolong_ha"], ids["rig_1"]),
            )
            await conn.execute(
                "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
                (pid, ids["rig_1"]),
            )
            await conn.commit()

            candidates = await load_project_rigs(conn, pid)

        assert len(candidates) == 1
        assert candidates[0].filter_ids == {ids["filter_optolong_ha"]}
        assert candidates[0].line_names == {"Ha"}

    async def test_single_filter_rig_is_eliminated_by_contradicting_line(self, client):
        """The loaded set must actually drive elimination, not just be populated."""
        ids = await _seed_equipment()
        pid = await _make_project(client, "SingleFilterElim")

        async with get_db() as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("DELETE FROM rig_filter_slot WHERE rig_id = ?", (ids["rig_1"],))
            await conn.execute(
                "UPDATE rig SET single_filter_id = ? WHERE id = ?",
                (ids["filter_optolong_ha"], ids["rig_1"]),
            )
            await conn.execute(
                "INSERT INTO project_rig (project_id, rig_id) VALUES (?, ?)",
                (pid, ids["rig_1"]),
            )
            await conn.commit()
            candidates = await load_project_rigs(conn, pid)

        # Ha matches the fixed filter → survives.
        assert (
            match_rig(
                candidates,
                camera_id=ids["camera_a"],
                camera_twin_key=None,
                focal_length_mm=None,
                line_name="Ha",
                filter_id=None,
            )
            is not None
        )
        # Sii contradicts the only filter this rig can carry → eliminated.
        assert (
            match_rig(
                candidates,
                camera_id=ids["camera_a"],
                camera_twin_key=None,
                focal_length_mm=None,
                line_name="Sii",
                filter_id=None,
            )
            is None
        )


class TestTwinCorrectionUnderUserRig:
    async def test_user_set_rig_still_corrects_the_camera_twin(self, client, tmp_path):
        """Manual rig override is exactly when auto-attribution failed — the
        two-camera correction has to run there too."""
        ids = await _seed_equipment(two_rigs=True)
        pid = await _make_project(client, "TwinUnderUserRig")
        await _assign_rigs(client, pid, [ids["rig_1"], ids["rig_2"]])

        folder = tmp_path / "capture"
        folder.mkdir()
        # 2800 mm → auto-attributes to rig_1, camera resolves to camera_a.
        _write_fits(folder / "light_001.fits", focallen=2800.0)
        await _ingest_folder(client, pid, folder)

        row = (await _frames(client, pid, frame_type="light"))[0]
        assert row["rig_id"] == ids["rig_1"]
        assert row["camera_id"] == ids["camera_a"]

        # User says it was really the Askar rig.
        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{row['id']}/equipment",
            json={"rig_id": ids["rig_2"]},
        )
        assert resp.status_code == 200, resp.text

        await client.post(f"/api/projects/{pid}/resolution/rerun")
        row = (await _frames(client, pid, frame_type="light"))[0]
        assert row["rig_id"] == ids["rig_2"], "user rig must survive the re-run"
        assert row["camera_id"] == ids["camera_b"], "camera must follow the user-set rig"
        assert row["rig_source"] == "user"

    async def test_user_set_camera_is_not_corrected(self, client, tmp_path):
        """A user-pinned camera stays put even when the rig implies a twin."""
        ids = await _seed_equipment(two_rigs=True)
        pid = await _make_project(client, "TwinUserCamera")
        await _assign_rigs(client, pid, [ids["rig_1"], ids["rig_2"]])

        folder = tmp_path / "capture"
        folder.mkdir()
        _write_fits(folder / "light_001.fits", focallen=2800.0)
        await _ingest_folder(client, pid, folder)
        row = (await _frames(client, pid, frame_type="light"))[0]

        resp = await client.patch(
            f"/api/projects/{pid}/catalog/frames/{row['id']}/equipment",
            json={"rig_id": ids["rig_2"], "camera_id": ids["camera_a"]},
        )
        assert resp.status_code == 200, resp.text

        await client.post(f"/api/projects/{pid}/resolution/rerun")
        row = (await _frames(client, pid, frame_type="light"))[0]
        assert row["camera_id"] == ids["camera_a"]
        assert row["camera_source"] == "user"


class TestLineNameAliasGuard:
    async def test_confirming_a_line_name_observation_is_422(self, client):
        """Legacy rows (queued before v0.41.0) must not become global aliases."""
        ids = await _seed_equipment()
        async with get_db() as conn:
            cursor = await conn.execute(
                "INSERT INTO unresolved_equipment_observation "
                "(equipment_kind, normalized_alias, original_observation, source) "
                "VALUES ('filter', 'ha', 'Ha', 'nina')"
            )
            obs_id = cursor.lastrowid
            await conn.commit()

        resp = await client.post(
            f"/api/equipment/unresolved/{obs_id}/confirm",
            json={"equipment_id": ids["filter_optolong_ha"]},
        )
        assert resp.status_code == 422
        assert "bandpass" in resp.json()["detail"]

        # Still unresolved, and no alias was created.
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT resolved_at FROM unresolved_equipment_observation WHERE id = ?",
                (obs_id,),
            )
            assert (await cursor.fetchone())["resolved_at"] is None
            cursor = await conn.execute("SELECT COUNT(*) AS n FROM filter_alias WHERE alias = 'ha'")
            assert (await cursor.fetchone())["n"] == 0

    async def test_physical_filter_name_still_confirms(self, client):
        """The guard must not block a real model-name alias."""
        ids = await _seed_equipment()
        async with get_db() as conn:
            cursor = await conn.execute(
                "INSERT INTO unresolved_equipment_observation "
                "(equipment_kind, normalized_alias, original_observation, source) "
                "VALUES ('filter', 'optolong l-pro', 'Optolong L-Pro', 'nina')"
            )
            obs_id = cursor.lastrowid
            await conn.commit()

        resp = await client.post(
            f"/api/equipment/unresolved/{obs_id}/confirm",
            json={"equipment_id": ids["filter_optolong_ha"]},
        )
        assert resp.status_code == 200, resp.text

    def test_migration_0042_covers_every_line_name_spelling(self):
        """The migration restates _LINE_NAME_MAP's keys in SQL — catch drift."""
        sql = (
            Path(__file__).resolve().parents[1]
            / "src/nightcrate/db/migrations/0042.purge_line_name_observations.sql"
        ).read_text()
        in_clause = sql.split("normalized_alias IN (", 1)[1].split(");", 1)[0]
        listed = set(re.findall(r"'([^']+)'", in_clause))
        assert listed == set(_LINE_NAME_MAP), (
            "migration 0042 and _LINE_NAME_MAP disagree; "
            f"missing={set(_LINE_NAME_MAP) - listed} extra={listed - set(_LINE_NAME_MAP)}"
        )
