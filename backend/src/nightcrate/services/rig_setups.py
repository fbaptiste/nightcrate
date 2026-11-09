"""Rig setup snapshots and usage calculations.

All functions use a caller-owned connection and deliberately never commit.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import aiosqlite

from nightcrate.services.ingest_sessions import observing_night, project_geo_timezone

PART_GROUPS: tuple[str, ...] = (
    "telescope",
    "camera",
    "filters",
    "mount",
    "focuser",
    "guider",
    "guide_camera",
    "computer",
    "software",
)

GROUP_COLUMNS: dict[str, tuple[str, ...]] = {
    "telescope": ("telescope_configuration_id",),
    "camera": ("camera_id",),
    "filters": ("filter_wheel_id", "single_filter_id", "filter_slots"),
    "mount": ("mount_id",),
    "focuser": ("focuser_id",),
    "guider": ("oag_id", "guide_scope_id"),
    "guide_camera": ("guide_camera_id",),
    "computer": ("computer_id",),
    "software": ("software_ids",),
}

_PART_COLUMNS = (
    "telescope_configuration_id",
    "camera_id",
    "filter_wheel_id",
    "single_filter_id",
    "mount_id",
    "focuser_id",
    "oag_id",
    "guide_scope_id",
    "guide_camera_id",
    "computer_id",
)


@dataclass(frozen=True)
class RigParts:
    telescope_configuration_id: int
    camera_id: int
    filter_wheel_id: int | None = None
    single_filter_id: int | None = None
    mount_id: int | None = None
    focuser_id: int | None = None
    oag_id: int | None = None
    guide_scope_id: int | None = None
    guide_camera_id: int | None = None
    computer_id: int | None = None
    filter_slots: frozenset[tuple[int, int]] = frozenset()
    software_ids: frozenset[int] = frozenset()

    def group_value(self, group: str) -> tuple:
        """Return the comparable value of one independently corrected group."""
        try:
            columns = GROUP_COLUMNS[group]
        except KeyError as exc:
            raise ValueError(f"unknown rig part group: {group}") from exc
        return tuple(getattr(self, column) for column in columns)

    def with_group(self, group: str, other: RigParts) -> RigParts:
        """Return a copy whose named group comes from *other*."""
        try:
            columns = GROUP_COLUMNS[group]
        except KeyError as exc:
            raise ValueError(f"unknown rig part group: {group}") from exc
        return replace(self, **{column: getattr(other, column) for column in columns})


@dataclass(frozen=True)
class RigUsage:
    project_count: int
    night_count: int


@dataclass(frozen=True)
class RigSetupSummary:
    id: int
    until_at: str
    parts: RigParts
    project_count: int
    night_count: int


@dataclass(frozen=True)
class ProjectSetup:
    rig_setup_id: int | None
    until_at: str | None
    since_at: str | None
    parts: RigParts
    night_count: int


@dataclass(frozen=True)
class ProjectSetupOption:
    rig_setup_id: int | None
    until_at: str | None
    parts: RigParts


@dataclass(frozen=True)
class ProjectRigSetups:
    rig_id: int
    rig_name: str
    declared: bool
    setups: tuple[ProjectSetup, ...]
    setup_options: tuple[ProjectSetupOption, ...]
    base_parts: RigParts
    change: RigParts | None
    changed_groups: tuple[str, ...]


async def _fetch_parts(
    conn: aiosqlite.Connection,
    *,
    row_id: int,
    label: str,
    parts_query: str,
    slots_query: str,
    software_query: str,
) -> RigParts:
    cursor = await conn.execute(parts_query, (row_id,))
    row = await cursor.fetchone()
    if row is None:
        raise ValueError(f"{label} {row_id} does not exist")

    cursor = await conn.execute(slots_query, (row_id,))
    slots = frozenset((item["slot_number"], item["filter_id"]) for item in await cursor.fetchall())
    cursor = await conn.execute(software_query, (row_id,))
    software_ids = frozenset(item["software_id"] for item in await cursor.fetchall())
    return RigParts(
        **{column: row[column] for column in _PART_COLUMNS},
        filter_slots=slots,
        software_ids=software_ids,
    )


async def read_rig_parts(conn: aiosqlite.Connection, rig_id: int) -> RigParts:
    return await _fetch_parts(
        conn,
        row_id=rig_id,
        label="rig",
        parts_query="""
            SELECT telescope_configuration_id, camera_id, filter_wheel_id,
                   single_filter_id, mount_id, focuser_id, oag_id, guide_scope_id,
                   guide_camera_id, computer_id
            FROM rig WHERE id = ?
        """,
        slots_query="""
            SELECT slot_number, filter_id FROM rig_filter_slot
            WHERE rig_id = ? ORDER BY slot_number
        """,
        software_query="SELECT software_id FROM rig_software WHERE rig_id = ?",
    )


async def read_setup_parts(conn: aiosqlite.Connection, rig_setup_id: int) -> RigParts:
    return await _fetch_parts(
        conn,
        row_id=rig_setup_id,
        label="rig_setup",
        parts_query="""
            SELECT telescope_configuration_id, camera_id, filter_wheel_id,
                   single_filter_id, mount_id, focuser_id, oag_id, guide_scope_id,
                   guide_camera_id, computer_id
            FROM rig_setup WHERE id = ?
        """,
        slots_query="""
            SELECT slot_number, filter_id FROM rig_setup_filter_slot
            WHERE rig_setup_id = ? ORDER BY slot_number
        """,
        software_query="""
            SELECT software_id FROM rig_setup_software WHERE rig_setup_id = ?
        """,
    )


def changed_groups(old: RigParts, new: RigParts) -> list[str]:
    return [group for group in PART_GROUPS if old.group_value(group) != new.group_value(group)]


async def _record_nights(
    conn: aiosqlite.Connection,
    frame_rows: list,
    batch_rows: list,
    session_rows: list | None = None,
) -> set[tuple[int, str]]:
    """Return distinct project nights represented by frames, batches, and sessions."""
    nights: set[tuple[int, str]] = set()
    timezones: dict[int, str | None] = {}
    for row in frame_rows:
        if row["date_obs_utc"] is None:
            continue
        project_id = row["project_id"]
        if project_id not in timezones:
            timezones[project_id] = await project_geo_timezone(conn, project_id)
        nights.add((project_id, observing_night(row["date_obs_utc"], timezones[project_id])))
    for row in batch_rows:
        if row["session_date"] is not None:
            nights.add((row["project_id"], row["session_date"][:10]))
    for row in session_rows or []:
        if row["start_utc"] is None:
            continue
        project_id = row["project_id"]
        if project_id not in timezones:
            timezones[project_id] = await project_geo_timezone(conn, project_id)
        nights.add((project_id, observing_night(row["start_utc"], timezones[project_id])))
    return nights


async def rig_usage(conn: aiosqlite.Connection, rig_id: int) -> RigUsage:
    cursor = await conn.execute(
        """
        SELECT project_id FROM project_rig WHERE rig_id = ?
        UNION SELECT project_id FROM project_session WHERE rig_id = ?
        UNION SELECT project_id FROM session WHERE rig_id = ? AND project_id IS NOT NULL
        UNION SELECT project_id FROM sub_frame WHERE rig_id = ?
        UNION SELECT project_id FROM project_source_folder WHERE rig_id = ?
        """,
        (rig_id, rig_id, rig_id, rig_id, rig_id),
    )
    projects = {row["project_id"] for row in await cursor.fetchall()}

    cursor = await conn.execute(
        """
        SELECT sf.project_id, sf.date_obs_utc
        FROM sub_frame sf
        WHERE sf.rig_id = ?
           OR (
               sf.rig_id IS NULL
               AND (SELECT COUNT(*) FROM project_rig pr WHERE pr.project_id = sf.project_id) = 1
               AND EXISTS (
                   SELECT 1 FROM project_rig pr
                   WHERE pr.project_id = sf.project_id AND pr.rig_id = ?
               )
           )
        """,
        (rig_id, rig_id),
    )
    frame_rows = await cursor.fetchall()

    cursor = await conn.execute(
        "SELECT project_id, session_date FROM project_session "
        "WHERE rig_id = ? AND session_date IS NOT NULL",
        (rig_id,),
    )
    batch_rows = await cursor.fetchall()
    cursor = await conn.execute(
        "SELECT project_id, start_utc FROM session "
        "WHERE rig_id = ? AND project_id IS NOT NULL AND start_utc IS NOT NULL",
        (rig_id,),
    )
    session_rows = await cursor.fetchall()
    nights = await _record_nights(conn, frame_rows, batch_rows, session_rows)
    return RigUsage(project_count=len(projects), night_count=len(nights))


async def save_earlier_setup(conn: aiosqlite.Connection, rig_id: int, *, until_at: str) -> int:
    parts = await read_rig_parts(conn, rig_id)
    cursor = await conn.execute(
        """
        INSERT INTO rig_setup (
            rig_id, until_at, telescope_configuration_id, camera_id,
            filter_wheel_id, single_filter_id, mount_id, focuser_id, oag_id,
            guide_scope_id, guide_camera_id, computer_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (rig_id, until_at, *(getattr(parts, column) for column in _PART_COLUMNS)),
    )
    rig_setup_id = cursor.lastrowid
    if rig_setup_id is None:
        raise RuntimeError("inserting rig setup did not return an id")

    await conn.executemany(
        "INSERT INTO rig_setup_filter_slot (rig_setup_id, slot_number, filter_id) VALUES (?, ?, ?)",
        [(rig_setup_id, slot, filter_id) for slot, filter_id in sorted(parts.filter_slots)],
    )
    await conn.executemany(
        "INSERT INTO rig_setup_software (rig_setup_id, software_id) VALUES (?, ?)",
        [(rig_setup_id, software_id) for software_id in sorted(parts.software_ids)],
    )

    await conn.execute(
        """
        INSERT INTO sub_frame_rig_setup (sub_frame_id, rig_id, rig_setup_id)
        SELECT sf.id, ?, ?
        FROM sub_frame sf
        WHERE (
            sf.rig_id = ?
            OR (
                sf.rig_id IS NULL
                AND (SELECT COUNT(*) FROM project_rig pr WHERE pr.project_id = sf.project_id) = 1
                AND EXISTS (
                    SELECT 1 FROM project_rig pr
                    WHERE pr.project_id = sf.project_id AND pr.rig_id = ?
                )
            )
        )
        AND NOT EXISTS (
            SELECT 1 FROM sub_frame_rig_setup sfs
            WHERE sfs.sub_frame_id = sf.id AND sfs.rig_id = ?
        )
        """,
        (rig_id, rig_setup_id, rig_id, rig_id, rig_id),
    )
    await conn.execute(
        """
        UPDATE project_session AS ps
        SET rig_setup_id = ?
        WHERE ps.rig_id = ?
          AND (
              ps.rig_setup_id IS NULL
              OR NOT EXISTS (
                  SELECT 1 FROM rig_setup rs
                  WHERE rs.id = ps.rig_setup_id AND rs.rig_id = ps.rig_id
              )
          )
        """,
        (rig_setup_id, rig_id),
    )
    return rig_setup_id


async def frame_setup_rig_ids(conn: aiosqlite.Connection, project_id: int) -> dict[int, int | None]:
    cursor = await conn.execute(
        "SELECT rig_id FROM project_rig WHERE project_id = ? ORDER BY rig_id LIMIT 2",
        (project_id,),
    )
    project_rigs = await cursor.fetchall()
    fallback = project_rigs[0]["rig_id"] if len(project_rigs) == 1 else None
    cursor = await conn.execute(
        "SELECT id, rig_id FROM sub_frame WHERE project_id = ? ORDER BY id", (project_id,)
    )
    return {
        row["id"]: row["rig_id"] if row["rig_id"] is not None else fallback
        for row in await cursor.fetchall()
    }


async def write_setup_parts(conn: aiosqlite.Connection, rig_setup_id: int, parts: RigParts) -> None:
    cursor = await conn.execute(
        """
        UPDATE rig_setup SET
            telescope_configuration_id = ?, camera_id = ?, filter_wheel_id = ?,
            single_filter_id = ?, mount_id = ?, focuser_id = ?, oag_id = ?,
            guide_scope_id = ?, guide_camera_id = ?, computer_id = ?
        WHERE id = ?
        """,
        (*(getattr(parts, column) for column in _PART_COLUMNS), rig_setup_id),
    )
    if cursor.rowcount == 0:
        raise ValueError(f"rig_setup {rig_setup_id} does not exist")
    await conn.execute("DELETE FROM rig_setup_filter_slot WHERE rig_setup_id = ?", (rig_setup_id,))
    await conn.executemany(
        "INSERT INTO rig_setup_filter_slot (rig_setup_id, slot_number, filter_id) VALUES (?, ?, ?)",
        [(rig_setup_id, slot, filter_id) for slot, filter_id in sorted(parts.filter_slots)],
    )
    await conn.execute("DELETE FROM rig_setup_software WHERE rig_setup_id = ?", (rig_setup_id,))
    await conn.executemany(
        "INSERT INTO rig_setup_software (rig_setup_id, software_id) VALUES (?, ?)",
        [(rig_setup_id, software_id) for software_id in sorted(parts.software_ids)],
    )


async def apply_correction_to_earlier_setups(
    conn: aiosqlite.Connection, rig_id: int, old: RigParts, new: RigParts
) -> int:
    groups = changed_groups(old, new)
    if not groups:
        return 0
    cursor = await conn.execute("SELECT id FROM rig_setup WHERE rig_id = ? ORDER BY id", (rig_id,))
    setup_ids = [row["id"] for row in await cursor.fetchall()]
    updated = 0
    for setup_id in setup_ids:
        current = await read_setup_parts(conn, setup_id)
        corrected = current
        for group in groups:
            if current.group_value(group) == old.group_value(group):
                corrected = corrected.with_group(group, new)
        if corrected != current:
            await write_setup_parts(conn, setup_id, corrected)
            updated += 1
    return updated


async def _setup_usage(conn: aiosqlite.Connection, rig_id: int, rig_setup_id: int) -> RigUsage:
    cursor = await conn.execute(
        """
        SELECT sf.project_id, sf.date_obs_utc
        FROM sub_frame_rig_setup sfs
        JOIN sub_frame sf ON sf.id = sfs.sub_frame_id
        WHERE sfs.rig_id = ? AND sfs.rig_setup_id = ?
          AND (
              sf.rig_id = ?
              OR (
                  sf.rig_id IS NULL
                  AND (SELECT COUNT(*) FROM project_rig pr WHERE pr.project_id = sf.project_id) = 1
                  AND EXISTS (
                      SELECT 1 FROM project_rig pr
                      WHERE pr.project_id = sf.project_id AND pr.rig_id = ?
                  )
              )
          )
        """,
        (rig_id, rig_setup_id, rig_id, rig_id),
    )
    frame_rows = await cursor.fetchall()
    cursor = await conn.execute(
        "SELECT project_id, session_date FROM project_session "
        "WHERE rig_id = ? AND rig_setup_id = ?",
        (rig_id, rig_setup_id),
    )
    batch_rows = await cursor.fetchall()

    projects = {row["project_id"] for row in frame_rows}
    projects.update(row["project_id"] for row in batch_rows)
    nights = await _record_nights(conn, frame_rows, batch_rows)
    return RigUsage(project_count=len(projects), night_count=len(nights))


async def list_rig_setups(conn: aiosqlite.Connection, rig_id: int) -> list[RigSetupSummary]:
    cursor = await conn.execute(
        "SELECT id, until_at FROM rig_setup WHERE rig_id = ? ORDER BY until_at DESC, id DESC",
        (rig_id,),
    )
    summaries: list[RigSetupSummary] = []
    for row in await cursor.fetchall():
        usage = await _setup_usage(conn, rig_id, row["id"])
        summaries.append(
            RigSetupSummary(
                id=row["id"],
                until_at=row["until_at"],
                parts=await read_setup_parts(conn, row["id"]),
                project_count=usage.project_count,
                night_count=usage.night_count,
            )
        )
    return summaries


async def _read_project_change(
    conn: aiosqlite.Connection, project_id: int, rig_id: int, base: RigParts
) -> tuple[RigParts | None, tuple[str, ...]]:
    cursor = await conn.execute(
        "SELECT * FROM project_rig_change WHERE project_id = ? AND rig_id = ?",
        (project_id, rig_id),
    )
    row = await cursor.fetchone()
    if row is None:
        return None, ()

    values = {column: getattr(base, column) for column in _PART_COLUMNS}
    groups: list[str] = []
    for group in PART_GROUPS:
        if group in {"telescope", "camera"}:
            column = GROUP_COLUMNS[group][0]
            changed = row[column] is not None
        else:
            changed = bool(row[f"{group}_changed"])
        if not changed:
            continue
        groups.append(group)
        for column in GROUP_COLUMNS[group]:
            if column not in {"filter_slots", "software_ids"}:
                values[column] = row[column]

    filter_slots = base.filter_slots
    if "filters" in groups:
        cursor = await conn.execute(
            "SELECT slot_number, filter_id FROM project_rig_change_filter_slot "
            "WHERE project_id = ? AND rig_id = ?",
            (project_id, rig_id),
        )
        filter_slots = frozenset(
            (item["slot_number"], item["filter_id"]) for item in await cursor.fetchall()
        )
    software_ids = base.software_ids
    if "software" in groups:
        cursor = await conn.execute(
            "SELECT software_id FROM project_rig_change_software "
            "WHERE project_id = ? AND rig_id = ?",
            (project_id, rig_id),
        )
        software_ids = frozenset(item["software_id"] for item in await cursor.fetchall())

    return (
        RigParts(**values, filter_slots=filter_slots, software_ids=software_ids),
        tuple(groups),
    )


async def project_setups(conn: aiosqlite.Connection, project_id: int) -> list[ProjectRigSetups]:
    """Return every rig/setup used by a project, with project changes applied."""
    cursor = await conn.execute("SELECT id FROM project WHERE id = ?", (project_id,))
    if await cursor.fetchone() is None:
        raise LookupError(f"project not found: {project_id}")

    cursor = await conn.execute(
        "SELECT rig_id FROM project_rig WHERE project_id = ?", (project_id,)
    )
    declared_ids = {row["rig_id"] for row in await cursor.fetchall()}
    setup_rigs = await frame_setup_rig_ids(conn, project_id)

    cursor = await conn.execute(
        "SELECT id, date_obs_utc FROM sub_frame WHERE project_id = ?", (project_id,)
    )
    frame_rows = await cursor.fetchall()
    cursor = await conn.execute(
        "SELECT sub_frame_id, rig_id, rig_setup_id FROM sub_frame_rig_setup "
        "WHERE sub_frame_id IN (SELECT id FROM sub_frame WHERE project_id = ?)",
        (project_id,),
    )
    frame_stamps = {
        (row["sub_frame_id"], row["rig_id"]): row["rig_setup_id"] for row in await cursor.fetchall()
    }
    cursor = await conn.execute(
        "SELECT rig_id, rig_setup_id, session_date FROM project_session "
        "WHERE project_id = ? AND rig_id IS NOT NULL",
        (project_id,),
    )
    batch_rows = await cursor.fetchall()

    rig_ids = set(declared_ids)
    rig_ids.update(rig_id for rig_id in setup_rigs.values() if rig_id is not None)
    rig_ids.update(row["rig_id"] for row in batch_rows)
    if not rig_ids:
        return []

    tz_name = await project_geo_timezone(conn, project_id)
    used: dict[tuple[int, int | None], set[str]] = {}
    for row in frame_rows:
        rig_id = setup_rigs[row["id"]]
        if rig_id is None:
            continue
        setup_id = frame_stamps.get((row["id"], rig_id))
        nights = used.setdefault((rig_id, setup_id), set())
        if row["date_obs_utc"] is not None:
            nights.add(observing_night(row["date_obs_utc"], tz_name))
    for row in batch_rows:
        nights = used.setdefault((row["rig_id"], row["rig_setup_id"]), set())
        if row["session_date"] is not None:
            nights.add(row["session_date"][:10])

    results: list[ProjectRigSetups] = []
    rig_orders: dict[int, int] = {}
    for rig_id in rig_ids:
        cursor = await conn.execute("SELECT name, sort_order FROM rig WHERE id = ?", (rig_id,))
        rig = await cursor.fetchone()
        if rig is None:
            continue
        rig_orders[rig_id] = rig["sort_order"]
        base = await read_rig_parts(conn, rig_id)
        change, groups = await _read_project_change(conn, project_id, rig_id, base)

        cursor = await conn.execute(
            "SELECT id, until_at FROM rig_setup WHERE rig_id = ? ORDER BY until_at DESC, id DESC",
            (rig_id,),
        )
        earlier = await cursor.fetchall()
        until_by_id = {row["id"]: row["until_at"] for row in earlier}
        since_by_id: dict[int, str | None] = {}
        for index, row in enumerate(earlier):
            since_by_id[row["id"]] = (
                earlier[index + 1]["until_at"] if index + 1 < len(earlier) else None
            )

        all_ids = [None, *(row["id"] for row in earlier)]
        effective_by_id: dict[int | None, RigParts] = {}
        for setup_id in all_ids:
            parts = base if setup_id is None else await read_setup_parts(conn, setup_id)
            effective = parts
            if change is not None:
                for group in groups:
                    effective = effective.with_group(group, change)
            effective_by_id[setup_id] = effective

        setup_options = tuple(
            ProjectSetupOption(
                rig_setup_id=setup_id,
                until_at=until_by_id.get(setup_id),
                parts=effective_by_id[setup_id],
            )
            for setup_id in all_ids
        )

        used_keys = {setup_id for (used_rig, setup_id) in used if used_rig == rig_id}
        if not used_keys:
            used_keys = {None}
        ordered_ids = ([None] if None in used_keys else []) + [
            row["id"] for row in earlier if row["id"] in used_keys
        ]
        setup_items: list[ProjectSetup] = []
        for setup_id in ordered_ids:
            setup_items.append(
                ProjectSetup(
                    rig_setup_id=setup_id,
                    until_at=until_by_id.get(setup_id),
                    since_at=(earlier[0]["until_at"] if setup_id is None and earlier else None)
                    if setup_id is None
                    else since_by_id[setup_id],
                    parts=effective_by_id[setup_id],
                    night_count=len(used.get((rig_id, setup_id), set())),
                )
            )
        results.append(
            ProjectRigSetups(
                rig_id=rig_id,
                rig_name=rig["name"],
                declared=rig_id in declared_ids,
                setups=tuple(setup_items),
                setup_options=setup_options,
                base_parts=base,
                change=change,
                changed_groups=groups,
            )
        )

    results.sort(key=lambda item: (rig_orders[item.rig_id], item.rig_name.casefold(), item.rig_id))
    return results


async def equipment_usage(conn: aiosqlite.Connection, kind: str, item_id: int) -> tuple[int, int]:
    """Count rigs and projects whose resolved setup references an equipment item."""
    valid = {
        "camera",
        "sensor",
        "telescope",
        "telescope_configuration",
        "filter_wheel",
        "filter",
        "mount",
        "focuser",
        "oag",
        "guide_scope",
        "computer",
    }
    if kind not in valid:
        raise ValueError(f"unknown equipment kind: {kind}")

    camera_sensors: dict[int, set[int]] = {}
    configuration_telescopes: dict[int, int] = {}

    async def references(parts: RigParts) -> bool:
        if kind == "camera":
            return item_id in {parts.camera_id, parts.guide_camera_id}
        if kind == "sensor":
            for camera_id in {parts.camera_id, parts.guide_camera_id} - {None}:
                if camera_id not in camera_sensors:
                    cursor = await conn.execute(
                        "SELECT sensor_id, guide_sensor_id FROM camera WHERE id = ?",
                        (camera_id,),
                    )
                    row = await cursor.fetchone()
                    camera_sensors[camera_id] = (
                        {value for value in (row["sensor_id"], row["guide_sensor_id"]) if value}
                        if row
                        else set()
                    )
                if item_id in camera_sensors[camera_id]:
                    return True
            return False
        if kind == "telescope_configuration":
            return parts.telescope_configuration_id == item_id
        if kind == "telescope":
            config_id = parts.telescope_configuration_id
            if config_id not in configuration_telescopes:
                cursor = await conn.execute(
                    "SELECT telescope_id FROM telescope_configuration WHERE id = ?",
                    (config_id,),
                )
                row = await cursor.fetchone()
                configuration_telescopes[config_id] = row["telescope_id"] if row else -1
            return configuration_telescopes[config_id] == item_id
        if kind == "filter_wheel":
            return parts.filter_wheel_id == item_id
        if kind == "filter":
            return parts.single_filter_id == item_id or any(
                filter_id == item_id for _slot, filter_id in parts.filter_slots
            )
        return getattr(parts, f"{kind}_id") == item_id

    cursor = await conn.execute("SELECT id FROM rig")
    rig_ids = [row["id"] for row in await cursor.fetchall()]
    rig_parts = {rig_id: await read_rig_parts(conn, rig_id) for rig_id in rig_ids}

    cursor = await conn.execute("SELECT id, rig_id FROM rig_setup")
    setup_rows = await cursor.fetchall()
    setup_parts = {row["id"]: await read_setup_parts(conn, row["id"]) for row in setup_rows}
    setup_ids_by_rig: dict[int, list[int]] = {}
    for row in setup_rows:
        setup_ids_by_rig.setdefault(row["rig_id"], []).append(row["id"])

    cursor = await conn.execute("SELECT project_id, rig_id FROM project_rig_change")
    change_rows = await cursor.fetchall()
    changes: dict[tuple[int, int], tuple[RigParts, tuple[str, ...]]] = {}
    for row in change_rows:
        key = (row["project_id"], row["rig_id"])
        change, groups = await _read_project_change(
            conn, row["project_id"], row["rig_id"], rig_parts[row["rig_id"]]
        )
        if change is not None:
            changes[key] = (change, groups)

    reference_cache: dict[tuple[int, int | None, int | None], bool] = {}

    async def combination_references(
        rig_id: int, setup_id: int | None, change_project_id: int | None
    ) -> bool:
        key = (rig_id, setup_id, change_project_id)
        if key in reference_cache:
            return reference_cache[key]
        parts = rig_parts[rig_id] if setup_id is None else setup_parts[setup_id]
        if change_project_id is not None:
            change, groups = changes[(change_project_id, rig_id)]
            for group in groups:
                parts = parts.with_group(group, change)
        result = await references(parts)
        reference_cache[key] = result
        return result

    used_rigs: set[int] = set()
    change_projects_by_rig: dict[int, list[int]] = {}
    for project_id, rig_id in changes:
        change_projects_by_rig.setdefault(rig_id, []).append(project_id)
    for rig_id in rig_ids:
        combinations = [(setup_id, None) for setup_id in setup_ids_by_rig.get(rig_id, [])]
        combinations.append((None, None))
        combinations.extend(
            (None, project_id) for project_id in change_projects_by_rig.get(rig_id, [])
        )
        if any(
            [
                await combination_references(rig_id, setup_id, project_id)
                for setup_id, project_id in combinations
            ]
        ):
            used_rigs.add(rig_id)

    cursor = await conn.execute(
        """
        WITH declared_rigs AS (
            SELECT project_id, COUNT(*) AS rig_count, MIN(rig_id) AS only_rig_id
            FROM project_rig
            GROUP BY project_id
        ),
        resolved_frames AS (
            SELECT sf.id AS sub_frame_id,
                   sf.project_id,
                   COALESCE(
                       sf.rig_id,
                       CASE WHEN dr.rig_count = 1 THEN dr.only_rig_id END
                   ) AS rig_id
            FROM sub_frame sf
            LEFT JOIN declared_rigs dr ON dr.project_id = sf.project_id
        )
        SELECT rf.project_id, rf.rig_id, srs.rig_setup_id
        FROM resolved_frames rf
        LEFT JOIN sub_frame_rig_setup srs
          ON srs.sub_frame_id = rf.sub_frame_id AND srs.rig_id = rf.rig_id
        WHERE rf.rig_id IS NOT NULL
        GROUP BY rf.project_id, rf.rig_id, srs.rig_setup_id
        """
    )
    used_keys = {
        (row["project_id"], row["rig_id"], row["rig_setup_id"]) for row in await cursor.fetchall()
    }
    cursor = await conn.execute(
        "SELECT project_id, rig_id, rig_setup_id FROM project_session "
        "WHERE rig_id IS NOT NULL GROUP BY project_id, rig_id, rig_setup_id"
    )
    used_keys.update(
        (row["project_id"], row["rig_id"], row["rig_setup_id"]) for row in await cursor.fetchall()
    )
    recorded_pairs = {(project_id, rig_id) for project_id, rig_id, _setup_id in used_keys}
    cursor = await conn.execute("SELECT project_id, rig_id FROM project_rig")
    used_keys.update(
        (row["project_id"], row["rig_id"], None)
        for row in await cursor.fetchall()
        if (row["project_id"], row["rig_id"]) not in recorded_pairs
    )

    used_projects: set[int] = set()
    for project_id, rig_id, setup_id in used_keys:
        change_project_id = project_id if (project_id, rig_id) in changes else None
        if await combination_references(rig_id, setup_id, change_project_id):
            used_projects.add(project_id)
    if kind == "filter":
        cursor = await conn.execute(
            "SELECT DISTINCT project_id FROM project_session "
            "WHERE source = 'manual' AND filter_id = ?",
            (item_id,),
        )
        used_projects.update(row["project_id"] for row in await cursor.fetchall())
    return len(used_rigs), len(used_projects)


async def set_batch_setup(
    conn: aiosqlite.Connection,
    project_id: int,
    project_session_id: int,
    rig_setup_id: int | None,
) -> None:
    """Move a manual batch or a derived observing night to a setup."""
    cursor = await conn.execute(
        "SELECT * FROM project_session WHERE id = ? AND project_id = ?",
        (project_session_id, project_id),
    )
    batch = await cursor.fetchone()
    if batch is None:
        raise LookupError(f"session not found: {project_session_id}")

    rig_id = batch["rig_id"]
    if rig_setup_id is not None:
        cursor = await conn.execute("SELECT rig_id FROM rig_setup WHERE id = ?", (rig_setup_id,))
        setup = await cursor.fetchone()
        if setup is None or setup["rig_id"] != rig_id:
            raise ValueError("The setup must belong to the batch's rig")

    if batch["source"] == "manual":
        await conn.execute(
            "UPDATE project_session SET rig_setup_id = ? WHERE id = ?",
            (rig_setup_id, project_session_id),
        )
        return

    if rig_id is None or batch["session_date"] is None:
        if rig_setup_id is not None:
            raise ValueError("A derived batch without a rig cannot use an earlier setup")
        await conn.execute(
            "UPDATE project_session SET rig_setup_id = NULL WHERE id = ?",
            (project_session_id,),
        )
        return

    tz_name = await project_geo_timezone(conn, project_id)
    setup_rigs = await frame_setup_rig_ids(conn, project_id)
    cursor = await conn.execute(
        "SELECT id, date_obs_utc FROM sub_frame WHERE project_id = ?",
        (project_id,),
    )
    frame_ids = [
        row["id"]
        for row in await cursor.fetchall()
        if setup_rigs[row["id"]] == rig_id
        and observing_night(row["date_obs_utc"], tz_name) == batch["session_date"][:10]
    ]
    if rig_setup_id is None:
        await conn.executemany(
            "DELETE FROM sub_frame_rig_setup WHERE sub_frame_id = ? AND rig_id = ?",
            [(frame_id, rig_id) for frame_id in frame_ids],
        )
    else:
        await conn.executemany(
            "INSERT INTO sub_frame_rig_setup (sub_frame_id, rig_id, rig_setup_id) "
            "VALUES (?, ?, ?) ON CONFLICT(sub_frame_id, rig_id) "
            "DO UPDATE SET rig_setup_id = excluded.rig_setup_id",
            [(frame_id, rig_id, rig_setup_id) for frame_id in frame_ids],
        )
    await conn.execute(
        "UPDATE project_session SET rig_setup_id = ? "
        "WHERE project_id = ? AND source = 'auto' AND rig_id = ? AND session_date = ?",
        (rig_setup_id, project_id, rig_id, batch["session_date"]),
    )
