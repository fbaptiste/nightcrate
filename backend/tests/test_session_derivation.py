"""Tests for deriving imaging sessions from cataloged light frames (v0.41.1).

Two layers:
  * Pure grouping helpers (grain, coercion, canonical filter key) — no DB.
  * The service + endpoint against directly-inserted sub_frames, plus the rule
    that ingest never derives on its own.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.db.session import get_db
from nightcrate.main import app
from nightcrate.services.session_derivation import (
    coerce_binning,
    coerce_gain,
    derive_sessions,
    filter_key,
    group_key,
)
from tests.catalog_helpers import _make_project, _seed_rig, _write_fits

# ── Pure grouping helpers ────────────────────────────────────────────────────


class TestGroupingHelpers:
    @pytest.mark.parametrize(
        ("hint", "expected"),
        [
            ("Ha", "Ha"),
            ("H-alpha", "Ha"),
            ("  ha  ", "Ha"),
            ("Red", "R"),
            ("Lum", "Lum"),
            ("L-eXtreme", "l-extreme"),
            ("Antlia  ALP-T", "antlia alp-t"),
            ("", None),
            (None, None),
        ],
    )
    def test_filter_key(self, hint, expected):
        assert filter_key(hint) == expected

    def test_equivalent_spellings_share_a_key(self):
        assert filter_key("Ha") == filter_key("H-alpha") == filter_key("HYDROGEN ALPHA")

    @pytest.mark.parametrize(
        ("gain", "expected"),
        [(101.0, 101), (100, 100), (0.0, 0), (99.6, 100), (None, None), (-5.0, None)],
    )
    def test_coerce_gain(self, gain, expected):
        assert coerce_gain(gain) == expected

    @pytest.mark.parametrize(
        ("bx", "by", "expected"),
        [(1, 1, 1), (2, 2, 2), (1, 2, None), (None, None, None), (None, 1, None), (0, 0, None)],
    )
    def test_coerce_binning(self, bx, by, expected):
        assert coerce_binning(bx, by) == expected

    def test_gain_float_and_int_group_together(self):
        a = group_key("2026-03-15", "Ha", 300.0, 101.0, 1, 1)
        b = group_key("2026-03-15", "Ha", 300.0, 101, 1, 1)
        assert a == b

    def test_exposure_difference_splits(self):
        a = group_key("2026-03-15", "Ha", 300.0, 101.0, 1, 1)
        b = group_key("2026-03-15", "Ha", 120.0, 101.0, 1, 1)
        assert a != b


# ── Fixtures for the DB-backed tests ─────────────────────────────────────────


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _add_lights(
    project_id: int,
    *,
    count: int = 1,
    date_obs: str = "2026-03-15T23:30:00+00:00",
    filter_hint: str | None = "Ha",
    exposure: float = 300.0,
    gain: float | None = 101.0,
    binning: tuple[int | None, int | None] = (1, 1),
    frame_type: str = "light",
) -> None:
    """Insert *count* sub_frames directly — the derive reads the table, not files."""
    async with get_db() as conn:
        for _ in range(count):
            await conn.execute(
                "INSERT INTO sub_frame (project_id, content_hash, frame_type, "
                "filter_name_hint, exposure_seconds, gain, binning_x, binning_y, date_obs_utc) "
                "VALUES (?, lower(hex(randomblob(16))), ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    frame_type,
                    filter_hint,
                    exposure,
                    gain,
                    binning[0],
                    binning[1],
                    date_obs,
                ),
            )
        await conn.commit()


async def _derive(project_id: int, tz_name: str | None = None) -> dict:
    async with get_db() as conn:
        summary = await derive_sessions(conn, project_id, tz_name=tz_name)
        await conn.commit()
    return summary.model_dump()


async def _sessions(client: AsyncClient, project_id: int) -> list[dict]:
    resp = await client.get(f"/api/projects/{project_id}/sessions")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── The derivation ───────────────────────────────────────────────────────────


class TestDerivationGrain:
    async def test_identical_lights_collapse_to_one_session(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=3)

        summary = await _derive(pid)
        assert summary["lights_considered"] == 3
        assert summary["sessions_created"] == 1

        rows = await _sessions(client, pid)
        assert len(rows) == 1
        row = rows[0]
        assert row["num_subs"] == 3
        assert row["exposure_seconds"] == 300.0
        assert row["gain"] == 101
        assert row["binning"] == 1
        assert row["line_name"] == "Ha"
        assert row["filter_label"] == "Ha"
        assert row["session_date"] == "2026-03-15"
        assert row["source"] == "auto"
        assert row["integration_minutes"] == 15.0

    async def test_mixed_exposure_splits_the_night(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=5, exposure=60.0)
        await _add_lights(pid, count=3, exposure=300.0)

        await _derive(pid)

        rows = await _sessions(client, pid)
        assert len(rows) == 2
        assert sorted((r["exposure_seconds"], r["num_subs"]) for r in rows) == [
            (60.0, 5),
            (300.0, 3),
        ]

    async def test_mixed_gain_splits_the_night(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=4, gain=101.0)
        await _add_lights(pid, count=2, gain=200.0)

        await _derive(pid)

        rows = await _sessions(client, pid)
        assert sorted((r["gain"], r["num_subs"]) for r in rows) == [(101, 4), (200, 2)]

    async def test_separate_filters_and_nights_split(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=2, filter_hint="Ha", date_obs="2026-03-15T23:00:00+00:00")
        await _add_lights(pid, count=1, filter_hint="Oiii", date_obs="2026-03-15T23:00:00+00:00")
        await _add_lights(pid, count=4, filter_hint="Ha", date_obs="2026-03-16T23:00:00+00:00")

        await _derive(pid)

        rows = await _sessions(client, pid)
        assert len(rows) == 3
        assert sorted((r["session_date"], r["line_name"], r["num_subs"]) for r in rows) == [
            ("2026-03-15", "Ha", 2),
            ("2026-03-15", "Oiii", 1),
            ("2026-03-16", "Ha", 4),
        ]

    async def test_calibration_frames_never_produce_sessions(self, client):
        pid = await _make_project(client, "Derive Test")
        for frame_type in ("dark", "flat", "bias", "dark_flat", "unknown"):
            await _add_lights(pid, count=2, frame_type=frame_type)

        summary = await _derive(pid)
        assert summary["lights_considered"] == 0
        assert summary["sessions_created"] == 0
        assert await _sessions(client, pid) == []

    async def test_empty_project_derives_nothing(self, client):
        pid = await _make_project(client, "Derive Test")
        summary = await _derive(pid)
        assert summary == {
            "project_id": pid,
            "lights_considered": 0,
            "lights_skipped": 0,
            "sessions_replaced": 0,
            "sessions_created": 0,
            "manual_sessions_kept": 0,
        }


class TestFilterCanonicalization:
    async def test_equivalent_spellings_collapse(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=2, filter_hint="Ha")
        await _add_lights(pid, count=3, filter_hint="H-alpha")

        await _derive(pid)

        rows = await _sessions(client, pid)
        assert len(rows) == 1
        assert rows[0]["num_subs"] == 5
        assert rows[0]["line_name"] == "Ha"

    async def test_unrecognized_name_falls_back_to_other_but_keeps_the_label(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=2, filter_hint="L-eXtreme")

        await _derive(pid)

        row = (await _sessions(client, pid))[0]
        assert row["line_name"] == "other"
        assert row["filter_label"] == "L-eXtreme"

    async def test_two_unrecognized_names_stay_separate(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=2, filter_hint="L-eXtreme")
        await _add_lights(pid, count=3, filter_hint="ALP-T")

        await _derive(pid)

        rows = await _sessions(client, pid)
        assert sorted(r["filter_label"] for r in rows) == ["ALP-T", "L-eXtreme"]
        assert {r["line_name"] for r in rows} == {"other"}

    async def test_missing_filter_header(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=2, filter_hint=None)

        await _derive(pid)

        row = (await _sessions(client, pid))[0]
        assert row["line_name"] == "other"
        assert row["filter_label"] is None


class TestReplaceAndKeep:
    async def test_manual_sessions_survive_repeated_derives(self, client):
        pid = await _make_project(client, "Derive Test")
        resp = await client.post(
            f"/api/projects/{pid}/sessions",
            json={"line_name": "Lum", "exposure_seconds": 60, "num_subs": 90},
        )
        assert resp.status_code == 201, resp.text
        manual = resp.json()

        await _add_lights(pid, count=3)
        first = await _derive(pid)
        assert first["manual_sessions_kept"] == 1
        assert first["sessions_replaced"] == 0

        second = await _derive(pid)
        assert second["sessions_replaced"] == 1
        assert second["manual_sessions_kept"] == 1

        rows = await _sessions(client, pid)
        kept = [r for r in rows if r["source"] == "manual"]
        assert len(kept) == 1
        assert kept[0]["id"] == manual["id"]
        assert kept[0]["num_subs"] == 90
        assert kept[0]["line_name"] == "Lum"

    async def test_re_derive_is_idempotent(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=2, filter_hint="Ha")
        await _add_lights(pid, count=4, filter_hint="Oiii")

        await _derive(pid)
        before = [
            (r["session_date"], r["line_name"], r["exposure_seconds"], r["num_subs"])
            for r in await _sessions(client, pid)
        ]
        await _derive(pid)
        after = [
            (r["session_date"], r["line_name"], r["exposure_seconds"], r["num_subs"])
            for r in await _sessions(client, pid)
        ]
        assert before == after
        assert len(after) == 2

    async def test_derive_reflects_removed_frames(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=3)
        await _derive(pid)

        async with get_db() as conn:
            await conn.execute("DELETE FROM sub_frame WHERE project_id = ?", (pid,))
            await conn.commit()

        summary = await _derive(pid)
        assert summary["sessions_replaced"] == 1
        assert summary["sessions_created"] == 0
        assert await _sessions(client, pid) == []


class TestObservingNight:
    """The noon-to-noon rollback must use the site's geo timezone, not raw UTC."""

    async def test_utc_splits_the_pair_across_two_nights(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=1, date_obs="2026-03-16T01:00:00+00:00")
        await _add_lights(pid, count=1, date_obs="2026-03-16T13:00:00+00:00")

        await _derive(pid, tz_name="UTC")

        rows = await _sessions(client, pid)
        assert sorted(r["session_date"] for r in rows) == ["2026-03-15", "2026-03-16"]

    async def test_western_site_keeps_the_pair_in_one_night(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=1, date_obs="2026-03-16T01:00:00+00:00")
        await _add_lights(pid, count=1, date_obs="2026-03-16T13:00:00+00:00")

        await _derive(pid, tz_name="America/New_York")

        rows = await _sessions(client, pid)
        assert len(rows) == 1
        assert rows[0]["session_date"] == "2026-03-15"
        assert rows[0]["num_subs"] == 2


class TestSkippedFrames:
    async def test_zero_exposure_light_is_skipped_not_fatal(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=1, exposure=0.0)
        await _add_lights(pid, count=2, exposure=300.0)

        summary = await _derive(pid)
        assert summary["lights_considered"] == 3
        assert summary["lights_skipped"] == 1
        assert summary["sessions_created"] == 1

        rows = await _sessions(client, pid)
        assert len(rows) == 1
        assert rows[0]["num_subs"] == 2


class TestSingleRigAttribution:
    async def test_derived_row_inherits_the_projects_only_rig(self, client):
        pid = await _make_project(client, "Derive Test")
        rig_id = await _seed_rig("Solo Rig")
        resp = await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": [rig_id]})
        assert resp.status_code == 200, resp.text
        await _add_lights(pid, count=2)

        await _derive(pid)

        assert (await _sessions(client, pid))[0]["rig_id"] == rig_id

    async def test_two_rigs_leave_it_null(self, client):
        pid = await _make_project(client, "Derive Test")
        rigs = [await _seed_rig("Rig A"), await _seed_rig("Rig B")]
        resp = await client.put(f"/api/projects/{pid}/rigs", json={"rig_ids": rigs})
        assert resp.status_code == 200, resp.text
        await _add_lights(pid, count=2)

        await _derive(pid)

        assert (await _sessions(client, pid))[0]["rig_id"] is None


# ── Endpoint + the "ingest never derives" rule ───────────────────────────────


class TestDeriveEndpoint:
    async def test_derive_endpoint_creates_rows(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=3)

        resp = await client.post(f"/api/projects/{pid}/sessions/derive")
        assert resp.status_code == 200, resp.text
        assert resp.json()["sessions_created"] == 1

        rows = await _sessions(client, pid)
        assert len(rows) == 1
        assert rows[0]["source"] == "auto"

    async def test_unknown_project_404s(self, client):
        resp = await client.post("/api/projects/999999/sessions/derive")
        assert resp.status_code == 404

    async def test_derived_rows_are_read_only(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=2)
        await client.post(f"/api/projects/{pid}/sessions/derive")
        session_id = (await _sessions(client, pid))[0]["id"]

        resp = await client.patch(
            f"/api/projects/{pid}/sessions/{session_id}", json={"num_subs": 99}
        )
        assert resp.status_code == 409
        assert "Catalog tab" in resp.json()["detail"]

        resp = await client.delete(f"/api/projects/{pid}/sessions/{session_id}")
        assert resp.status_code == 409

        assert (await _sessions(client, pid))[0]["num_subs"] == 2

    async def test_integration_reflects_derived_rows(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=4, filter_hint="Ha", exposure=300.0)
        await _add_lights(pid, count=2, filter_hint="L-eXtreme", exposure=600.0)
        await client.post(f"/api/projects/{pid}/sessions/derive")

        resp = await client.get(f"/api/projects/{pid}/integration")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["total_actual_minutes"] == 40.0
        by_label = {line["label"]: line for line in body["lines"]}
        assert by_label["Ha"]["actual_minutes"] == 20.0
        assert by_label["Ha"]["sub_count"] == 4
        assert by_label["Ha"]["session_count"] == 1
        # An unrecognized filter name is labelled by itself, not lumped into "other".
        assert by_label["L-eXtreme"]["actual_minutes"] == 20.0
        # Goals are gone from the wire entirely.
        assert all("goal_minutes" not in line for line in body["lines"])

    async def test_split_night_counts_as_one_session(self, client):
        pid = await _make_project(client, "Derive Test")
        await _add_lights(pid, count=4, exposure=300.0)
        await _add_lights(pid, count=2, exposure=60.0)
        await client.post(f"/api/projects/{pid}/sessions/derive")

        resp = await client.get(f"/api/projects/{pid}/integration")
        line = resp.json()["lines"][0]
        assert line["sub_count"] == 6
        assert line["session_count"] == 1  # two rows, one night


class TestIngestDoesNotDerive:
    """Cataloging frames must never create sessions on its own — a project may
    hold no subs at all and still keep a hand-entered session record."""

    async def test_scan_leaves_sessions_empty(self, client, tmp_path: Path):
        pid = await _make_project(client, "Derive Test")
        folder = tmp_path / "lights"
        folder.mkdir()
        for i in range(3):
            _write_fits(folder / f"light_{i}.fits")

        resp = await client.post(f"/api/projects/{pid}/folders", json={"path": str(folder)})
        assert resp.status_code == 201, resp.text
        resp = await client.post(f"/api/projects/{pid}/ingest")
        assert resp.status_code == 200, resp.text
        assert resp.json()["subs_inserted"] == 3

        assert await _sessions(client, pid) == []

        # ...and the explicit derive then picks them up.
        resp = await client.post(f"/api/projects/{pid}/sessions/derive")
        assert resp.json()["sessions_created"] == 1
        assert len(await _sessions(client, pid)) == 1


# ── Source-folder rig tag ────────────────────────────────────────────────────


class TestFolderRigTag:
    """The rig on a source folder is the one equipment fact the ingest records, and
    the user declares it. Frames inherit it, sessions split on it, and calibration
    refuses to cross rigs."""

    async def test_frames_inherit_the_folders_rig_and_sessions_split(self, client, tmp_path: Path):
        pid = await _make_project(client, "Derive Test")
        rig_a, rig_b = await _seed_rig("Rig A"), await _seed_rig("Rig B")

        # Two rigs shooting the same target the same night, into one project.
        folders = {}
        for name, rig in (("rigA", rig_a), ("rigB", rig_b)):
            folder = tmp_path / name
            folder.mkdir()
            for i in range(2):
                _write_fits(folder / f"{name}_{i}.fits")
            resp = await client.post(
                f"/api/projects/{pid}/folders", json={"path": str(folder), "rig_id": rig}
            )
            assert resp.status_code == 201, resp.text
            assert resp.json()["rig_id"] == rig
            folders[name] = resp.json()["id"]

        resp = await client.post(f"/api/projects/{pid}/ingest")
        assert resp.status_code == 200, resp.text

        async with get_db() as conn:
            cur = await conn.execute(
                "SELECT rig_id, COUNT(*) n FROM sub_frame WHERE project_id = ? GROUP BY rig_id",
                (pid,),
            )
            by_rig = {r["rig_id"]: r["n"] for r in await cur.fetchall()}
            assert by_rig == {rig_a: 2, rig_b: 2}
            # Same night, two rigs → two sessions, never conflated.
            cur = await conn.execute(
                "SELECT rig_id FROM session WHERE project_id = ? ORDER BY rig_id", (pid,)
            )
            assert [r["rig_id"] for r in await cur.fetchall()] == sorted([rig_a, rig_b])

    async def test_tagging_after_the_fact_retags_and_rekeys(self, client, tmp_path: Path):
        pid = await _make_project(client, "Derive Test")
        rig = await _seed_rig("Late Rig")
        folder = tmp_path / "untagged"
        folder.mkdir()
        for i in range(3):
            _write_fits(folder / f"l{i}.fits")
        resp = await client.post(f"/api/projects/{pid}/folders", json={"path": str(folder)})
        folder_id = resp.json()["id"]
        assert resp.json()["rig_id"] is None
        await client.post(f"/api/projects/{pid}/ingest")

        async with get_db() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) n FROM sub_frame WHERE project_id = ? AND rig_id IS NULL", (pid,)
            )
            assert (await cur.fetchone())["n"] == 3

        # Tag it afterwards — no re-scan required.
        resp = await client.patch(f"/api/projects/{pid}/folders/{folder_id}", json={"rig_id": rig})
        assert resp.status_code == 200, resp.text
        assert resp.json()["rig_id"] == rig
        assert resp.json()["rig_name"] == "Late Rig"

        async with get_db() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) n FROM sub_frame WHERE project_id = ? AND rig_id = ?", (pid, rig)
            )
            assert (await cur.fetchone())["n"] == 3
            cur = await conn.execute("SELECT rig_id FROM session WHERE project_id = ?", (pid,))
            rows = await cur.fetchall()
            assert [r["rig_id"] for r in rows] == [rig], "the session must be re-keyed too"

    async def test_clearing_the_tag(self, client, tmp_path: Path):
        pid = await _make_project(client, "Derive Test")
        rig = await _seed_rig("Temp Rig")
        folder = tmp_path / "clearme"
        folder.mkdir()
        _write_fits(folder / "l0.fits")
        resp = await client.post(
            f"/api/projects/{pid}/folders", json={"path": str(folder), "rig_id": rig}
        )
        folder_id = resp.json()["id"]
        await client.post(f"/api/projects/{pid}/ingest")

        resp = await client.patch(f"/api/projects/{pid}/folders/{folder_id}", json={"rig_id": None})
        assert resp.status_code == 200, resp.text
        assert resp.json()["rig_id"] is None
        async with get_db() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) n FROM sub_frame WHERE project_id = ? AND rig_id IS NOT NULL",
                (pid,),
            )
            assert (await cur.fetchone())["n"] == 0

    async def test_nested_folders_resolve_innermost_first(self, client, tmp_path: Path):
        """Binding a parent and a child folder must give the nested files the CHILD's
        rig, whatever order the folders were added, scanned or tagged in. A naive
        prefix match lets the parent steal them (or last-writer-wins on scan)."""
        pid = await _make_project(client, "Nested")
        outer_rig, inner_rig = await _seed_rig("Outer Rig"), await _seed_rig("Inner Rig")

        outer = tmp_path / "data"
        inner = outer / "rig-b"
        inner.mkdir(parents=True)
        _write_fits(outer / "outer.fits")
        _write_fits(inner / "inner.fits")

        # Deliberately bind the CHILD first, so "last added wins" would be wrong.
        await client.post(
            f"/api/projects/{pid}/folders", json={"path": str(inner), "rig_id": inner_rig}
        )
        outer_resp = await client.post(
            f"/api/projects/{pid}/folders", json={"path": str(outer), "rig_id": outer_rig}
        )
        await client.post(f"/api/projects/{pid}/ingest")

        async def rigs_by_file() -> dict[str, int | None]:
            async with get_db() as conn:
                cur = await conn.execute(
                    "SELECT fl.path, sf.rig_id FROM sub_frame sf "
                    "JOIN file_location fl ON fl.sub_frame_id = sf.id WHERE sf.project_id = ?",
                    (pid,),
                )
                return {Path(r["path"]).name: r["rig_id"] for r in await cur.fetchall()}

        assert await rigs_by_file() == {"outer.fits": outer_rig, "inner.fits": inner_rig}

        # Re-tagging the PARENT must not steal the child's frames either.
        resp = await client.patch(
            f"/api/projects/{pid}/folders/{outer_resp.json()['id']}", json={"rig_id": outer_rig}
        )
        assert resp.status_code == 200, resp.text
        assert await rigs_by_file() == {"outer.fits": outer_rig, "inner.fits": inner_rig}

        # And a re-scan is stable rather than flip-flopping.
        await client.post(f"/api/projects/{pid}/ingest")
        assert await rigs_by_file() == {"outer.fits": outer_rig, "inner.fits": inner_rig}

    async def test_unknown_rig_404s(self, client, tmp_path: Path):
        pid = await _make_project(client, "Derive Test")
        folder = tmp_path / "f"
        folder.mkdir()
        resp = await client.post(f"/api/projects/{pid}/folders", json={"path": str(folder)})
        folder_id = resp.json()["id"]
        resp = await client.patch(
            f"/api/projects/{pid}/folders/{folder_id}", json={"rig_id": 999999}
        )
        assert resp.status_code == 404

    async def test_derived_sessions_still_group_by_night_and_filter(self, client, tmp_path: Path):
        """A rig tag must not fragment the derived sessions — those key on night +
        filter + capture settings, not on the rig."""
        pid = await _make_project(client, "Derive Test")
        rig = await _seed_rig("Only Rig")
        folder = tmp_path / "solo"
        folder.mkdir()
        for i in range(4):
            _write_fits(folder / f"l{i}.fits")
        await client.post(f"/api/projects/{pid}/folders", json={"path": str(folder), "rig_id": rig})
        await client.post(f"/api/projects/{pid}/ingest")
        await client.post(f"/api/projects/{pid}/sessions/derive")

        rows = await _sessions(client, pid)
        assert len(rows) == 1
        assert rows[0]["num_subs"] == 4
        assert rows[0]["rig_id"] == rig
