"""Project-scoped rig attribution + equipment re-resolution (v0.41.0).

Answers "which of this project's rigs captured this frame?" and re-runs the
equipment resolver over everything a project has already cataloged — so newly
confirmed aliases and newly assigned rigs propagate without a re-scan.

Design rules (settled 2026-07-08, PLAN.md v0.41.0):

- **Project-scoped, never global.** Candidates are exactly the rigs assigned to
  the project via ``project_rig``. A project with no rigs assigned gets no
  discovery at all.
- **Eliminate, never guess.** Each available signal (camera, focal length,
  filter) can only *eliminate* a candidate rig. Exactly one survivor →
  attributed; zero or several survivors → the frame stays unattributed (NULL).
  A single-rig project therefore attributes everything that doesn't contradict
  that rig — which is what assigning the rig to the project *means*.
- **User overrides win.** Fields whose ``*_source`` column is ``'user'`` are
  never touched by this pass (migration 0041).
- **Sessions follow rigs.** Attribution re-keys each frame's auto-session to
  ``(rig, observing night)`` — dual-rig nights become two sessions, exactly as
  the ingest spec requires — and empty sessions are swept.

Pure service: no FastAPI, no imports from ``api/``. Caller owns the transaction
(same contract as ``equipment_resolver``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import aiosqlite

from nightcrate.services.equipment_resolver import (
    EquipmentResolver,
    RigContext,
    canonicalize_line_name,
)
from nightcrate.services.fits_header_map import extract_metadata
from nightcrate.services.ingest_models import AttributionSummary
from nightcrate.services.ingest_sessions import (
    ensure_session,
    session_key,
    sweep_empty_sessions,
)

logger = logging.getLogger("nightcrate.rig_attribution")

_LOG_PREFIX = "[rig-attribution]"

# Module-level tuples: ruff format strips parens from inline ``except (A, B):``
# on py3.14, producing invalid Py2 syntax. Referencing constants sidesteps it.
_BAD_JSON = (json.JSONDecodeError, TypeError)
_BAD_NUMBER = (TypeError, ValueError)

# Header FOCALLEN is user-entered nominal (ASIAir: "600") while the rig's
# telescope_configuration carries the measured effective value (e.g. 608 mm), so
# equality is hopeless but a ±5 % band cleanly separates real configurations
# (C11 at 2800 mm vs Askar V at ~600 mm) without false-eliminating nominal
# entries.
_FOCAL_TOLERANCE = 0.05

# Filters only exist on lights and flats (calibration darks/bias are filterless
# by definition — mirrors the ingest keeps_filter rule).
_FILTERED_FRAME_TYPES = ("light", "flat")


# A frame camera and a rig camera are "same-model twins" when they share
# manufacturer + sensor. Two physical bodies of one model are necessarily two
# rows with distinct model_names (camera has UNIQUE(manufacturer_id,
# model_name)), so name equality can't express twin-ness — but the sensor FK
# can, deterministically (no string similarity, per the no-fuzzy-matching rule).
CameraTwinKey = tuple[int, int]  # (manufacturer_id, sensor_id)


@dataclass
class RigCandidate:
    """One project rig with the signals attribution can match against."""

    rig_id: int
    camera_id: int
    camera_twin_key: CameraTwinKey
    focal_length_mm: float
    single_filter_id: int | None = None
    filter_ids: set[int] = field(default_factory=set)
    line_names: set[str] = field(default_factory=set)


async def load_project_rigs(conn: aiosqlite.Connection, project_id: int) -> list[RigCandidate]:
    """The project's assigned rigs with camera, focal length, and filter loadout."""
    cursor = await conn.execute(
        "SELECT r.id, r.camera_id, r.single_filter_id, c.manufacturer_id, c.sensor_id, "
        "tc.effective_focal_length_mm "
        "FROM project_rig pr "
        "JOIN rig r ON r.id = pr.rig_id "
        "JOIN camera c ON c.id = r.camera_id "
        "JOIN telescope_configuration tc ON tc.id = r.telescope_configuration_id "
        "WHERE pr.project_id = ? AND r.active = 1 "
        "ORDER BY r.id",
        (project_id,),
    )
    candidates = [
        RigCandidate(
            rig_id=row["id"],
            camera_id=row["camera_id"],
            camera_twin_key=(row["manufacturer_id"], row["sensor_id"]),
            focal_length_mm=row["effective_focal_length_mm"],
            single_filter_id=row["single_filter_id"],
        )
        for row in await cursor.fetchall()
    ]
    for cand in candidates:
        # A rig carries filters EITHER through a wheel (rig_filter_slot) OR as one
        # fixed filter (rig.single_filter_id) — api/rigs.py enforces that they're
        # mutually exclusive. Both must feed the loadout, or a wheel-less rig has
        # an empty filter set and the filter signal can never eliminate it.
        cursor = await conn.execute(
            "SELECT f.id AS filter_id, fp.line_name "
            "FROM filter f "
            "LEFT JOIN filter_passband fp ON fp.filter_id = f.id AND fp.active = 1 "
            "WHERE f.id IN (SELECT filter_id FROM rig_filter_slot WHERE rig_id = ?) "
            "   OR f.id = ?",
            (cand.rig_id, cand.single_filter_id),
        )
        for row in await cursor.fetchall():
            cand.filter_ids.add(row["filter_id"])
            if row["line_name"]:
                cand.line_names.add(row["line_name"])
    return candidates


def match_rig(
    candidates: list[RigCandidate],
    *,
    camera_id: int | None,
    camera_twin_key: CameraTwinKey | None,
    focal_length_mm: float | None,
    line_name: str | None,
    filter_id: int | None,
) -> RigCandidate | None:
    """Attribute a frame to exactly one candidate rig, or return ``None``.

    Every signal the frame carries must be *consistent* with a candidate for it
    to survive; missing signals are neutral. The camera signal is satisfied by
    the exact camera **or a same-model twin** (shared manufacturer + sensor) —
    two physical bodies of the same model emit an identical ``INSTRUME``, so
    the alias always resolves to one of them and an id-only comparison would
    wrongly eliminate the other body's rig (the §7 two-camera problem).
    ``filter_id`` (a user-asserted physical filter) takes precedence over
    ``line_name`` (parsed from the raw ``FILTER`` header).
    """
    survivors = []
    for cand in candidates:
        if camera_id is not None and camera_id != cand.camera_id:
            if camera_twin_key is None or camera_twin_key != cand.camera_twin_key:
                continue
        if focal_length_mm is not None and not _focal_matches(
            focal_length_mm, cand.focal_length_mm
        ):
            continue
        if cand.filter_ids:
            if filter_id is not None:
                if filter_id not in cand.filter_ids:
                    continue
            elif line_name is not None and line_name not in cand.line_names:
                continue
        survivors.append(cand)
    if len(survivors) == 1:
        return survivors[0]
    return None


def _focal_matches(header_mm: float, rig_mm: float) -> bool:
    if rig_mm <= 0:
        return False
    return abs(header_mm - rig_mm) / rig_mm <= _FOCAL_TOLERANCE


async def rerun_resolution(
    conn: aiosqlite.Connection,
    project_id: int,
    *,
    tz_name: str | None,
) -> AttributionSummary:
    """Re-resolve equipment + attribute rigs across a project's whole catalog.

    Idempotent: running it twice in a row leaves the catalog unchanged. Fields
    with ``*_source = 'user'`` are preserved. Sessions are re-keyed to the final
    ``(rig, observing night)`` and empty auto-sessions swept. Caller owns the
    transaction.
    """
    candidates = await load_project_rigs(conn, project_id)
    resolver = EquipmentResolver(conn)
    summary = AttributionSummary(rigs_considered=len(candidates))
    camera_twins: dict[int, CameraTwinKey] = {}  # camera_id → twin key (memo)

    cursor = await conn.execute(
        "SELECT id, frame_type, fits_header_json, filter_name_hint, date_obs_utc, "
        "camera_id, camera_source, telescope_id, filter_id, filter_source, "
        "rig_id, rig_source, session_id "
        "FROM sub_frame WHERE project_id = ? ORDER BY id",
        (project_id,),
    )
    frames = await cursor.fetchall()

    for row in frames:
        summary.frames_processed += 1
        raw = _load_header(row["fits_header_json"])
        meta = extract_metadata(raw)

        camera_id = row["camera_id"]
        camera_twin_key: CameraTwinKey | None = None
        if row["camera_source"] != "user":
            res = await resolver.resolve_camera(meta.get("camera_name"), source="manual")
            camera_id = res.equipment_id
            if res.equipment is not None:
                camera_twin_key = (
                    res.equipment["manufacturer_id"],
                    res.equipment["sensor_id"],
                )
        if camera_id is not None and camera_twin_key is None:
            camera_twin_key = await _camera_twin_key(conn, camera_id, camera_twins)

        res = await resolver.resolve_telescope(meta.get("telescope_name"), source="manual")
        telescope_id = res.equipment_id

        keeps_filter = row["frame_type"] in _FILTERED_FRAME_TYPES
        hint_line = canonicalize_line_name(row["filter_name_hint"] or "") if keeps_filter else None

        rig_id = row["rig_id"]
        if row["rig_source"] == "user":
            # The user pinned the rig — keep it, but still look the candidate up so
            # the camera correction below applies. A rig outside the project's
            # assigned set has no candidate; the user is the authority, so the rig
            # stands and only the correction is skipped.
            cand = next((c for c in candidates if c.rig_id == rig_id), None)
        else:
            cand = match_rig(
                candidates,
                camera_id=camera_id,
                camera_twin_key=camera_twin_key,
                focal_length_mm=_as_float(meta.get("focal_length")),
                line_name=hint_line,
                filter_id=row["filter_id"] if row["filter_source"] == "user" else None,
            )
            rig_id = cand.rig_id if cand is not None else None

        # Two-camera disambiguation (§7 payoff): the shared-model alias always
        # resolves to one physical body; once the rig is known — whether matched
        # here or pinned by the user — correct the camera to the rig's actual
        # same-model body. A user-set camera is never touched.
        if (
            cand is not None
            and row["camera_source"] != "user"
            and camera_id is not None
            and camera_id != cand.camera_id
            and camera_twin_key == cand.camera_twin_key
        ):
            camera_id = cand.camera_id
            summary.cameras_rig_corrected += 1

        filter_id = row["filter_id"]
        if row["filter_source"] != "user":
            if not keeps_filter:
                filter_id = None
            else:
                ctx = RigContext(rig_id=rig_id) if rig_id is not None else None
                res = await resolver.resolve_filter(
                    row["filter_name_hint"], source="manual", rig_context=ctx
                )
                filter_id = res.equipment_id

        changed = (
            camera_id != row["camera_id"]
            or telescope_id != row["telescope_id"]
            or filter_id != row["filter_id"]
            or rig_id != row["rig_id"]
        )
        if changed:
            await conn.execute(
                "UPDATE sub_frame SET camera_id = ?, telescope_id = ?, filter_id = ?, "
                "rig_id = ? WHERE id = ?",
                (camera_id, telescope_id, filter_id, rig_id, row["id"]),
            )
            summary.frames_changed += 1

        if camera_id is not None:
            summary.cameras_resolved += 1
        if telescope_id is not None:
            summary.telescopes_resolved += 1
        if keeps_filter and filter_id is not None:
            summary.filters_resolved += 1
        if rig_id is not None:
            summary.rigs_attributed += 1

        # Sessions follow the final rig: re-key to (rig, observing night).
        key = session_key(rig_id, row["date_obs_utc"], tz_name)
        session_id = await ensure_session(conn, project_id, key, tz_name)
        if session_id != row["session_id"]:
            await conn.execute(
                "UPDATE sub_frame SET session_id = ? WHERE id = ?",
                (session_id, row["id"]),
            )

    await _rerun_masters(conn, project_id, resolver, candidates, summary)

    # Sweep auto-sessions the re-keying emptied.
    await sweep_empty_sessions(conn, project_id)

    logger.info(
        "%s project %d: frames=%d changed=%d rigs_attributed=%d filters=%d "
        "cameras=%d masters=%d (candidates=%d)",
        _LOG_PREFIX,
        project_id,
        summary.frames_processed,
        summary.frames_changed,
        summary.rigs_attributed,
        summary.filters_resolved,
        summary.cameras_resolved,
        summary.masters_processed,
        len(candidates),
    )
    return summary


async def _rerun_masters(
    conn: aiosqlite.Connection,
    project_id: int,
    resolver: EquipmentResolver,
    candidates: list[RigCandidate],
    summary: AttributionSummary,
) -> None:
    """Re-resolve camera/telescope/filter on masters (no rig column on masters).

    Filter line-name scoping needs a rig; a master spans the whole project, so it
    only gets a context when the project has exactly one candidate rig.
    """
    master_ctx = RigContext(rig_id=candidates[0].rig_id) if len(candidates) == 1 else None
    cursor = await conn.execute(
        "SELECT id, frame_type, fits_header_json, camera_id, telescope_id, "
        "filter_id, line_name FROM processed_image WHERE project_id = ? ORDER BY id",
        (project_id,),
    )
    for row in await cursor.fetchall():
        summary.masters_processed += 1
        raw = _load_header(row["fits_header_json"])
        meta = extract_metadata(raw)

        res = await resolver.resolve_camera(meta.get("camera_name"), source="manual")
        camera_id = res.equipment_id
        res = await resolver.resolve_telescope(meta.get("telescope_name"), source="manual")
        telescope_id = res.equipment_id

        filter_id = row["filter_id"]
        line_name = row["line_name"]
        if row["frame_type"] in _FILTERED_FRAME_TYPES:
            res = await resolver.resolve_filter(
                meta.get("filter_name"), source="manual", rig_context=master_ctx
            )
            filter_id = res.equipment_id
            # line_name is the display fallback for unresolved master filters
            # (mirrors ingest's _upsert_processed): resolved → clear it.
            line_name = (
                None if filter_id is not None else canonicalize_line_name(raw.get("FILTER") or "")
            )

        if (
            camera_id != row["camera_id"]
            or telescope_id != row["telescope_id"]
            or filter_id != row["filter_id"]
            or line_name != row["line_name"]
        ):
            await conn.execute(
                "UPDATE processed_image SET camera_id = ?, telescope_id = ?, "
                "filter_id = ?, line_name = ? WHERE id = ?",
                (camera_id, telescope_id, filter_id, line_name, row["id"]),
            )
            summary.masters_changed += 1


async def _camera_twin_key(
    conn: aiosqlite.Connection, camera_id: int, memo: dict[int, CameraTwinKey]
) -> CameraTwinKey | None:
    """(manufacturer_id, sensor_id) for a camera id (memoized per pass)."""
    if camera_id not in memo:
        cursor = await conn.execute(
            "SELECT manufacturer_id, sensor_id FROM camera WHERE id = ?", (camera_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        memo[camera_id] = (row["manufacturer_id"], row["sensor_id"])
    return memo[camera_id]


def _load_header(header_json: str | None) -> dict:
    if not header_json:
        return {}
    try:
        loaded = json.loads(header_json)
    except _BAD_JSON:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except _BAD_NUMBER:
        return None
