"""Move user-owned references when two catalog objects become one."""

from __future__ import annotations

import sqlite3

CATALOG_DERIVED_TABLES: frozenset[str] = frozenset(
    {"dso_designation", "dso_external_ref", "thumbnail_cache"}
)
USER_LINK_TABLES: frozenset[str] = frozenset({"favorite_target", "project_target", "project_dso"})


def _tables(cur: sqlite3.Cursor) -> tuple[str, ...]:
    cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    return tuple(str(row[0]) for row in cur.fetchall())


def _foreign_keys_to(
    cur: sqlite3.Cursor, parent: str, parent_column: str = "id"
) -> tuple[tuple[str, str], ...]:
    found: list[tuple[str, str]] = []
    for table in _tables(cur):
        cur.execute(f'PRAGMA foreign_key_list("{table}")')  # nosec B608
        for row in cur.fetchall():
            if row[2] == parent and row[4] in (None, parent_column):
                found.append((table, str(row[3])))
    return tuple(found)


def count_references(cur: sqlite3.Cursor, dso_id: int) -> int:
    """Count non-catalog rows with a direct foreign key to ``dso(id)``."""
    total = 0
    for table, column in _foreign_keys_to(cur, "dso"):
        if table in CATALOG_DERIVED_TABLES:
            continue
        cur.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" = ?',  # nosec B608
            (dso_id,),
        )
        total += int(cur.fetchone()[0])
    return total


def _merge_ranges(cur: sqlite3.Cursor, survivor_plan_id: int, old_plan_id: int) -> None:
    cur.execute(
        """
        SELECT start_date, end_date
        FROM target_plan_date_range
        WHERE plan_id IN (?, ?)
        ORDER BY start_date, end_date
        """,
        (survivor_plan_id, old_plan_id),
    )
    merged: list[list[str]] = []
    for start, end in cur.fetchall():
        if merged and str(start) <= merged[-1][1]:
            if str(end) > merged[-1][1]:
                merged[-1][1] = str(end)
        else:
            merged.append([str(start), str(end)])
    cur.execute(
        "DELETE FROM target_plan_date_range WHERE plan_id IN (?, ?)",
        (survivor_plan_id, old_plan_id),
    )
    cur.executemany(
        """
        INSERT INTO target_plan_date_range (plan_id, start_date, end_date)
        VALUES (?, ?, ?)
        """,
        ((survivor_plan_id, start, end) for start, end in merged),
    )


def _merge_plan(
    cur: sqlite3.Cursor, old_plan: sqlite3.Row, survivor_plan: sqlite3.Row, old_label: str
) -> None:
    notes: list[str] = []
    if survivor_plan["notes"]:
        notes.append(str(survivor_plan["notes"]))
    if old_plan["notes"]:
        notes.append(f"From {old_label}: {old_plan['notes']}")

    metadata_columns = {
        "id",
        "dso_id",
        "location_id",
        "horizon_id",
        "rig_id",
        "notes",
        "created_at",
        "updated_at",
    }
    differences = [
        f"{column}={old_plan[column]}"
        for column in old_plan.keys()
        if column not in metadata_columns and old_plan[column] != survivor_plan[column]
    ]
    if differences:
        notes.append(f"From {old_label}, settings not kept: {', '.join(differences)}")

    cur.execute(
        "UPDATE target_plan SET notes = ? WHERE id = ?",
        ("\n\n".join(notes) or None, survivor_plan["id"]),
    )
    _merge_ranges(cur, int(survivor_plan["id"]), int(old_plan["id"]))
    cur.execute("DELETE FROM target_plan WHERE id = ?", (old_plan["id"],))


def _move_favorite(cur: sqlite3.Cursor, old_id: int, new_id: int, old_label: str) -> None:
    cur.execute("SELECT * FROM favorite_target WHERE dso_id = ?", (old_id,))
    old_favorite = cur.fetchone()
    if old_favorite is None:
        return
    cur.execute("SELECT * FROM favorite_target WHERE dso_id = ?", (new_id,))
    new_favorite = cur.fetchone()
    if new_favorite is None:
        cur.execute(
            """
            INSERT INTO favorite_target (dso_id, sort_order, section_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                new_id,
                old_favorite["sort_order"],
                old_favorite["section_id"],
                old_favorite["created_at"],
            ),
        )

    cur.execute("SELECT * FROM target_plan WHERE dso_id = ? ORDER BY id", (old_id,))
    for old_plan in cur.fetchall():
        cur.execute(
            """
            SELECT * FROM target_plan
            WHERE dso_id = ? AND location_id = ? AND horizon_id = ? AND rig_id = ?
            """,
            (
                new_id,
                old_plan["location_id"],
                old_plan["horizon_id"],
                old_plan["rig_id"],
            ),
        )
        survivor_plan = cur.fetchone()
        if survivor_plan is None:
            cur.execute("UPDATE target_plan SET dso_id = ? WHERE id = ?", (new_id, old_plan["id"]))
        else:
            _merge_plan(cur, old_plan, survivor_plan, old_label)
    cur.execute("DELETE FROM favorite_target WHERE dso_id = ?", (old_id,))


def _repoint_children(
    cur: sqlite3.Cursor, parent: str, old_parent_id: int, new_parent_id: int
) -> None:
    for table, column in _foreign_keys_to(cur, parent):
        cur.execute(
            f'UPDATE "{table}" SET "{column}" = ? WHERE "{column}" = ?',  # nosec B608
            (new_parent_id, old_parent_id),
        )


def _move_project_targets(cur: sqlite3.Cursor, old_id: int, new_id: int) -> None:
    cur.execute("SELECT * FROM project_target WHERE dso_id = ? ORDER BY id", (old_id,))
    for old_target in cur.fetchall():
        cur.execute(
            "SELECT * FROM project_target WHERE project_id = ? AND dso_id = ?",
            (old_target["project_id"], new_id),
        )
        survivor = cur.fetchone()
        if survivor is None:
            cur.execute(
                "UPDATE project_target SET dso_id = ? WHERE id = ?",
                (new_id, old_target["id"]),
            )
            continue
        _repoint_children(cur, "project_target", int(old_target["id"]), int(survivor["id"]))
        cur.execute("DELETE FROM project_target WHERE id = ?", (old_target["id"],))


def _move_project_dsos(cur: sqlite3.Cursor, old_id: int, new_id: int) -> None:
    cur.execute("SELECT * FROM project_dso WHERE dso_id = ? ORDER BY id", (old_id,))
    for old_row in cur.fetchall():
        cur.execute(
            "SELECT * FROM project_dso WHERE solve_id = ? AND dso_id = ?",
            (old_row["solve_id"], new_id),
        )
        survivor = cur.fetchone()
        if survivor is None:
            cur.execute("UPDATE project_dso SET dso_id = ? WHERE id = ?", (new_id, old_row["id"]))
            continue
        if old_row["is_main"] and not survivor["is_main"]:
            cur.execute("UPDATE project_dso SET is_main = 1 WHERE id = ?", (survivor["id"],))
        cur.execute("DELETE FROM project_dso WHERE id = ?", (old_row["id"],))


def move_user_links(cur: sqlite3.Cursor, old_id: int, new_id: int, old_label: str) -> None:
    """Move known user links from *old_id* to *new_id* without committing."""
    _move_favorite(cur, old_id, new_id, old_label)
    _move_project_targets(cur, old_id, new_id)
    _move_project_dsos(cur, old_id, new_id)
