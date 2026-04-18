"""Core seed loader — loads CSV seed data into the equipment database.

Runs inside the caller's transaction. All FK resolution failures and
constraint violations are collected and raised as a group; the caller is
responsible for rolling back on failure.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from nightcrate.seed_loader.csv_reader import read_seed_csv
from nightcrate.seed_loader.hash import HASH_CONTRACT_VERSION, compute_seed_hash
from nightcrate.seed_loader.models import SeedError, SeedReport, TableReport
from nightcrate.seed_loader.registry import LOAD_ORDER, SeedableTable

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Maps SQLite declared type keywords → Python converter tag
_INT_TYPES = {"INTEGER", "INT", "SMALLINT", "TINYINT", "MEDIUMINT", "BIGINT"}
_REAL_TYPES = {"REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL"}

# Alias table names (no seed_key/seed_hash)
_ALIAS_SUFFIX = "_alias"


def _get_column_types(conn: sqlite3.Connection, table_name: str) -> dict[str, str]:
    """Return {column_name: 'int'|'real'|'text'} for every column in *table_name*.

    Uses PRAGMA table_info which returns the declared type string.  We
    normalise to one of three tags so the caller can do simple branching.
    """
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    result: dict[str, str] = {}
    for row in cursor.fetchall():
        col_name: str = row["name"]
        declared: str = (row["type"] or "").upper().split("(")[0].strip()
        if declared in _INT_TYPES:
            result[col_name] = "int"
        elif declared in _REAL_TYPES:
            result[col_name] = "real"
        else:
            result[col_name] = "text"
    return result


def _convert_value(raw: str | None, type_tag: str) -> int | float | str | None:
    """Convert a raw CSV string to the appropriate Python type."""
    if raw is None:
        return None
    if type_tag == "int":
        return int(raw)
    if type_tag == "real":
        return float(raw)
    return raw  # text — keep as-is


def _build_incoming(
    row: dict[str, str | None],
    table: SeedableTable,
    col_types: dict[str, str],
    fk_map: dict[tuple[str, str], int],
    conn: sqlite3.Connection,
    errors: list[SeedError],
    seed_key: str | None,
) -> dict[str, int | float | str | None] | None:
    """Resolve FKs and build the DB-column dict for *row*.

    Returns None if any FK resolution failed (errors appended in-place).
    """
    # Map csv_col → db_col for FK columns
    fk_csv_to_db: dict[str, str] = {}
    for csv_col in table.fk_columns:
        db_col = csv_col.replace("_seed_key", "_id")
        fk_csv_to_db[csv_col] = db_col

    incoming: dict[str, int | float | str | None] = {}
    ok = True

    # Seed-key and non-FK data fields
    for field_name in table.seeded_fields:
        # Is this field a DB FK column that we resolve from a CSV seed_key column?
        # Map: db_col → csv_col
        csv_col = None
        ref_table = None
        for c_csv, c_ref in table.fk_columns.items():
            if c_csv.replace("_seed_key", "_id") == field_name:
                csv_col = c_csv
                ref_table = c_ref
                break

        if csv_col is not None and ref_table is not None:
            # FK field — resolve from seed_key
            raw_sk = row.get(csv_col)
            if raw_sk is None:
                # Nullable FK — leave as None
                incoming[field_name] = None
            else:
                fk_cache_key = (ref_table, raw_sk)
                if fk_cache_key not in fk_map:
                    errors.append(
                        SeedError(
                            table=table.table_name,
                            seed_key=seed_key,
                            message=(
                                f"FK resolution failed: {ref_table} seed_key '{raw_sk}' "
                                f"not in fk_map (referenced by {csv_col})"
                            ),
                        )
                    )
                    ok = False
                else:
                    incoming[field_name] = fk_map[fk_cache_key]
        else:
            # Regular data field — type-convert from CSV string
            raw = row.get(field_name)
            type_tag = col_types.get(field_name, "text")
            incoming[field_name] = _convert_value(raw, type_tag)

    return incoming if ok else None


def _is_alias_table(table: SeedableTable) -> bool:
    return table.table_name.endswith(_ALIAS_SUFFIX)


def _is_child_table(table: SeedableTable) -> bool:
    return table.parent_key_column is not None and not table.is_junction


# ---------------------------------------------------------------------------
# Regular table: first-run insert
# ---------------------------------------------------------------------------


def _insert_row(
    conn: sqlite3.Connection,
    table_name: str,
    seed_key: str,
    incoming: dict,
    seed_hash: str,
) -> int:
    """INSERT a seed row; return the new row id."""
    cols = list(incoming.keys()) + ["source", "seed_key", "seed_hash"]
    vals = list(incoming.values()) + ["seed", seed_key, seed_hash]
    placeholders = ", ".join("?" for _ in cols)
    col_str = ", ".join(cols)
    conn.execute(
        f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders})",  # nosec B608 - table name from internal allow-list, not user input
        vals,
    )
    cur = conn.execute("SELECT last_insert_rowid()")
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_all(
    conn: sqlite3.Connection,
    csv_root: Path,
    mode: Literal["first_run", "update", "auto"] = "auto",
) -> SeedReport:
    """Load all seed data from CSV files into the database.

    Runs inside the caller's transaction. Raises on fatal errors
    (caller should rollback). Returns SeedReport with per-table results.
    """
    # ------------------------------------------------------------------
    # Determine mode
    # ------------------------------------------------------------------
    meta_row = conn.execute(
        "SELECT value FROM seed_loader_meta WHERE key = 'first_seeded_at'"
    ).fetchone()

    if mode == "auto":
        effective_mode: Literal["first_run", "update"] = (
            "update" if meta_row is not None else "first_run"
        )
    else:
        effective_mode = mode  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Hash contract version check on update
    # ------------------------------------------------------------------
    if effective_mode == "update":
        hcv_row = conn.execute(
            "SELECT value FROM seed_loader_meta WHERE key = 'hash_contract_version'"
        ).fetchone()
        if hcv_row is None:
            raise RuntimeError(
                "seed_loader_meta is missing hash_contract_version — cannot re-seed safely"
            )
        stored_hcv = hcv_row["value"]
        if stored_hcv != HASH_CONTRACT_VERSION:
            raise RuntimeError(
                f"Hash contract version mismatch: stored={stored_hcv!r}, "
                f"current={HASH_CONTRACT_VERSION!r}. "
                f"Run a migration to re-hash all seed rows before re-seeding."
            )

    report = SeedReport(mode=effective_mode)

    # ------------------------------------------------------------------
    # In-memory FK map: (table_name, seed_key) → id
    # ------------------------------------------------------------------
    fk_map: dict[tuple[str, str], int] = {}

    # Track which parents were inserted or updated (for junction/child decisions)
    # { table_name: set of seed_keys }
    inserted_or_updated: dict[str, set[str]] = {}

    # Collect all errors; raise at end if any
    errors: list[SeedError] = []

    # ------------------------------------------------------------------
    # Process tables in load order
    # ------------------------------------------------------------------
    for table in LOAD_ORDER:
        csv_path = csv_root / table.csv_filename
        if not csv_path.exists():
            # No CSV file — skip silently
            continue

        rows = read_seed_csv(csv_path, table)
        if not rows:
            # Empty CSV — skip
            continue

        col_types = _get_column_types(conn, table.table_name)

        if table.is_junction:
            _load_junction_table(
                conn=conn,
                table=table,
                rows=rows,
                fk_map=fk_map,
                col_types=col_types,
                inserted_or_updated=inserted_or_updated,
                report=report,
                errors=errors,
            )
        elif _is_alias_table(table):
            _load_alias_table(
                conn=conn,
                table=table,
                rows=rows,
                fk_map=fk_map,
                col_types=col_types,
                report=report,
                errors=errors,
            )
        elif _is_child_table(table):
            _load_child_table(
                conn=conn,
                table=table,
                rows=rows,
                fk_map=fk_map,
                col_types=col_types,
                inserted_or_updated=inserted_or_updated,
                effective_mode=effective_mode,
                report=report,
                errors=errors,
            )
        else:
            _load_regular_table(
                conn=conn,
                table=table,
                rows=rows,
                fk_map=fk_map,
                col_types=col_types,
                inserted_or_updated=inserted_or_updated,
                effective_mode=effective_mode,
                report=report,
                errors=errors,
            )

    # ------------------------------------------------------------------
    # Raise if any errors were collected
    # ------------------------------------------------------------------
    if errors:
        report.errors = errors
        raise RuntimeError(
            f"Seed loader failed with {len(errors)} error(s): "
            + "; ".join(f"[{e.table}] {e.message}" for e in errors[:5])
            + (" ..." if len(errors) > 5 else "")
        )

    # ------------------------------------------------------------------
    # Update seed_loader_meta
    # ------------------------------------------------------------------
    now_iso = datetime.now(UTC).isoformat()
    if effective_mode == "first_run":
        conn.execute(
            "INSERT OR REPLACE INTO seed_loader_meta (key, value) VALUES (?, ?)",
            ("hash_contract_version", HASH_CONTRACT_VERSION),
        )
        conn.execute(
            "INSERT OR REPLACE INTO seed_loader_meta (key, value) VALUES (?, ?)",
            ("first_seeded_at", now_iso),
        )
        conn.execute(
            "INSERT OR REPLACE INTO seed_loader_meta (key, value) VALUES (?, ?)",
            ("last_seeded_at", now_iso),
        )
    else:
        conn.execute(
            "INSERT OR REPLACE INTO seed_loader_meta (key, value) VALUES (?, ?)",
            ("last_seeded_at", now_iso),
        )

    report.finished_at = datetime.now()
    return report


# ---------------------------------------------------------------------------
# Regular table loader
# ---------------------------------------------------------------------------


def _load_regular_table(
    conn: sqlite3.Connection,
    table: SeedableTable,
    rows: list[dict],
    fk_map: dict[tuple[str, str], int],
    col_types: dict[str, str],
    inserted_or_updated: dict[str, set[str]],
    effective_mode: Literal["first_run", "update"],
    report: SeedReport,
    errors: list[SeedError],
) -> None:
    table_report = TableReport()
    csv_seed_keys: set[str] = set()
    table_inserted_or_updated: set[str] = set()

    for row in rows:
        seed_key: str = row["seed_key"]  # type: ignore[assignment]
        csv_seed_keys.add(seed_key)

        incoming = _build_incoming(
            row=row,
            table=table,
            col_types=col_types,
            fk_map=fk_map,
            conn=conn,
            errors=errors,
            seed_key=seed_key,
        )
        if incoming is None:
            # FK resolution failed — error already appended
            continue

        incoming_hash = compute_seed_hash(incoming)

        if effective_mode == "first_run":
            try:
                row_id = _insert_row(conn, table.table_name, seed_key, incoming, incoming_hash)
            except sqlite3.IntegrityError as exc:
                errors.append(
                    SeedError(
                        table=table.table_name,
                        seed_key=seed_key,
                        message=f"INSERT failed: {exc}",
                        exception=str(exc),
                    )
                )
                continue
            fk_map[(table.table_name, seed_key)] = row_id
            table_inserted_or_updated.add(seed_key)
            table_report.inserted += 1
        else:
            # Update mode
            existing = conn.execute(
                f"SELECT * FROM {table.table_name} WHERE seed_key = ?",  # nosec B608 - table name from internal allow-list, not user input
                (seed_key,),
            ).fetchone()

            if existing is None:
                # New row — insert
                try:
                    row_id = _insert_row(conn, table.table_name, seed_key, incoming, incoming_hash)
                except sqlite3.IntegrityError as exc:
                    errors.append(
                        SeedError(
                            table=table.table_name,
                            seed_key=seed_key,
                            message=f"INSERT failed: {exc}",
                            exception=str(exc),
                        )
                    )
                    continue
                fk_map[(table.table_name, seed_key)] = row_id
                table_inserted_or_updated.add(seed_key)
                table_report.inserted += 1
            else:
                existing_id: int = existing["id"]
                fk_map[(table.table_name, seed_key)] = existing_id

                if existing["source"] != "seed":
                    table_report.skipped_corrupt.append(seed_key)
                    continue

                # Build current_row from the seeded fields in the existing DB row
                current_row = {f: existing[f] for f in table.seeded_fields}
                current_hash = compute_seed_hash(current_row)

                if current_hash != existing["seed_hash"]:
                    # User has modified this row — skip
                    table_report.skipped_user_modified.append(seed_key)
                    continue

                if incoming_hash == existing["seed_hash"]:
                    # No change
                    table_report.unchanged += 1
                    continue

                # Update
                set_parts = [f"{col} = ?" for col in incoming]
                set_parts.append("seed_hash = ?")
                set_vals = list(incoming.values()) + [incoming_hash, existing_id]
                conn.execute(
                    f"UPDATE {table.table_name} SET {', '.join(set_parts)} WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                    set_vals,
                )
                table_inserted_or_updated.add(seed_key)
                table_report.updated += 1

    # Orphan detection (update mode only, for regular non-alias non-junction tables)
    if effective_mode == "update" and csv_seed_keys:
        placeholders = ",".join("?" for _ in csv_seed_keys)
        orphan_rows = conn.execute(
            f"SELECT seed_key FROM {table.table_name} "  # nosec B608 - table name from internal allow-list, not user input
            f"WHERE source = 'seed' AND seed_key NOT IN ({placeholders})",
            list(csv_seed_keys),
        ).fetchall()
        for orphan in orphan_rows:
            table_report.orphaned.append(orphan["seed_key"])

    inserted_or_updated[table.table_name] = table_inserted_or_updated
    report.per_table[table.table_name] = table_report


# ---------------------------------------------------------------------------
# Junction table loader
# ---------------------------------------------------------------------------


def _load_junction_table(
    conn: sqlite3.Connection,
    table: SeedableTable,
    rows: list[dict],
    fk_map: dict[tuple[str, str], int],
    col_types: dict[str, str],
    inserted_or_updated: dict[str, set[str]],
    report: SeedReport,
    errors: list[SeedError],
) -> None:
    """Junction tables: delete-and-reinsert for parents that changed."""
    table_report = TableReport()
    parent_table = table.junction_parent

    # Group CSV rows by parent seed_key
    parent_csv_col = next(c for c, ref in table.fk_columns.items() if ref == parent_table)
    parent_db_col = parent_csv_col.replace("_seed_key", "_id")

    groups: dict[str, list[dict]] = {}
    for row in rows:
        parent_sk: str = row[parent_csv_col]  # type: ignore[assignment]
        groups.setdefault(parent_sk, []).append(row)

    parent_changed = inserted_or_updated.get(parent_table, set())

    for parent_sk, group_rows in groups.items():
        if parent_sk not in parent_changed:
            # Parent unchanged — skip junction rows
            continue

        parent_id = fk_map.get((parent_table, parent_sk))
        if parent_id is None:
            errors.append(
                SeedError(
                    table=table.table_name,
                    seed_key=None,
                    message=(
                        f"Junction parent {parent_table} seed_key '{parent_sk}' not in fk_map"
                    ),
                )
            )
            continue

        # Delete existing junction rows for this parent
        conn.execute(
            f"DELETE FROM {table.table_name} WHERE {parent_db_col} = ?",  # nosec B608 - table name from internal allow-list, not user input
            (parent_id,),
        )

        # Insert new junction rows
        for jrow in group_rows:
            incoming = _build_incoming(
                row=jrow,
                table=table,
                col_types=col_types,
                fk_map=fk_map,
                conn=conn,
                errors=errors,
                seed_key=None,
            )
            if incoming is None:
                continue
            cols = list(incoming.keys())
            vals = list(incoming.values())
            placeholders = ", ".join("?" for _ in cols)
            col_str = ", ".join(cols)
            try:
                conn.execute(
                    f"INSERT INTO {table.table_name} ({col_str}) VALUES ({placeholders})",  # nosec B608 - table name from internal allow-list, not user input
                    vals,
                )
                table_report.inserted += 1
            except sqlite3.IntegrityError as exc:
                errors.append(
                    SeedError(
                        table=table.table_name,
                        seed_key=None,
                        message=f"Junction INSERT failed for parent '{parent_sk}': {exc}",
                        exception=str(exc),
                    )
                )

    report.per_table[table.table_name] = table_report


# ---------------------------------------------------------------------------
# Child table loader
# ---------------------------------------------------------------------------


def _load_child_table(
    conn: sqlite3.Connection,
    table: SeedableTable,
    rows: list[dict],
    fk_map: dict[tuple[str, str], int],
    col_types: dict[str, str],
    inserted_or_updated: dict[str, set[str]],
    effective_mode: Literal["first_run", "update"],
    report: SeedReport,
    errors: list[SeedError],
) -> None:
    """Child tables (telescope_configuration, filter_passband)."""
    table_report = TableReport()

    # Determine parent table from fk_columns using parent_key_column
    parent_csv_col = table.parent_key_column  # e.g. "telescope_seed_key"
    parent_ref = table.fk_columns[parent_csv_col]  # e.g. "telescope"
    parent_db_col = parent_csv_col.replace("_seed_key", "_id")  # e.g. "telescope_id"

    # Group rows by parent seed_key
    groups: dict[str, list[dict]] = {}
    for row in rows:
        parent_sk: str = row[parent_csv_col]  # type: ignore[assignment]
        groups.setdefault(parent_sk, []).append(row)

    for parent_sk, group_rows in groups.items():
        parent_id = fk_map.get((parent_ref, parent_sk))
        if parent_id is None:
            errors.append(
                SeedError(
                    table=table.table_name,
                    seed_key=None,
                    message=(f"Child parent {parent_ref} seed_key '{parent_sk}' not in fk_map"),
                )
            )
            continue

        if effective_mode == "first_run":
            # First run — no existing rows, blind insert is safe
            for child_row in group_rows:
                child_seed_key: str = child_row["seed_key"]  # type: ignore[assignment]
                incoming = _build_incoming(
                    row=child_row,
                    table=table,
                    col_types=col_types,
                    fk_map=fk_map,
                    conn=conn,
                    errors=errors,
                    seed_key=child_seed_key,
                )
                if incoming is None:
                    continue
                child_hash = compute_seed_hash(incoming)
                try:
                    row_id = _insert_row(
                        conn, table.table_name, child_seed_key, incoming, child_hash
                    )
                    fk_map[(table.table_name, child_seed_key)] = row_id
                    table_report.inserted += 1
                except sqlite3.IntegrityError as exc:
                    errors.append(
                        SeedError(
                            table=table.table_name,
                            seed_key=child_seed_key,
                            message=f"Child INSERT failed: {exc}",
                            exception=str(exc),
                        )
                    )
        else:
            # Parent was unchanged — apply child-level update logic per existing row
            csv_child_keys = {r["seed_key"] for r in group_rows}

            for child_row in group_rows:
                child_seed_key_val: str = child_row["seed_key"]  # type: ignore[assignment]
                incoming = _build_incoming(
                    row=child_row,
                    table=table,
                    col_types=col_types,
                    fk_map=fk_map,
                    conn=conn,
                    errors=errors,
                    seed_key=child_seed_key_val,
                )
                if incoming is None:
                    continue

                existing_child = conn.execute(
                    f"SELECT * FROM {table.table_name} WHERE seed_key = ?",  # nosec B608 - table name from internal allow-list, not user input
                    (child_seed_key_val,),
                ).fetchone()

                incoming_hash = compute_seed_hash(incoming)

                if existing_child is None:
                    # New child
                    try:
                        row_id = _insert_row(
                            conn,
                            table.table_name,
                            child_seed_key_val,
                            incoming,
                            incoming_hash,
                        )
                        fk_map[(table.table_name, child_seed_key_val)] = row_id
                        table_report.inserted += 1
                    except sqlite3.IntegrityError as exc:
                        errors.append(
                            SeedError(
                                table=table.table_name,
                                seed_key=child_seed_key_val,
                                message=f"Child INSERT failed: {exc}",
                                exception=str(exc),
                            )
                        )
                    continue

                existing_id: int = existing_child["id"]
                fk_map[(table.table_name, child_seed_key_val)] = existing_id

                if existing_child["source"] != "seed":
                    table_report.skipped_corrupt.append(child_seed_key_val)
                    continue

                current_row = {f: existing_child[f] for f in table.seeded_fields}
                current_hash = compute_seed_hash(current_row)

                if current_hash != existing_child["seed_hash"]:
                    table_report.skipped_user_modified.append(child_seed_key_val)
                    continue

                if incoming_hash == existing_child["seed_hash"]:
                    table_report.unchanged += 1
                    continue

                # Update child
                set_parts = [f"{col} = ?" for col in incoming]
                set_parts.append("seed_hash = ?")
                set_vals = list(incoming.values()) + [incoming_hash, existing_id]
                conn.execute(
                    f"UPDATE {table.table_name} SET {', '.join(set_parts)} WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                    set_vals,
                )
                fk_map[(table.table_name, child_seed_key_val)] = existing_id
                table_report.updated += 1

            # Orphan detection for children
            if effective_mode == "update" and csv_child_keys:
                placeholders = ",".join("?" for _ in csv_child_keys)
                orphan_rows = conn.execute(
                    f"SELECT seed_key FROM {table.table_name} "  # nosec B608 - table name from internal allow-list, not user input
                    f"WHERE {parent_db_col} = ? "
                    f"AND source = 'seed' "
                    f"AND seed_key NOT IN ({placeholders})",
                    [parent_id] + list(csv_child_keys),
                ).fetchall()
                for orphan in orphan_rows:
                    table_report.orphaned.append(orphan["seed_key"])

    report.per_table[table.table_name] = table_report


# ---------------------------------------------------------------------------
# Alias table loader
# ---------------------------------------------------------------------------


def _load_alias_table(
    conn: sqlite3.Connection,
    table: SeedableTable,
    rows: list[dict],
    fk_map: dict[tuple[str, str], int],
    col_types: dict[str, str],
    report: SeedReport,
    errors: list[SeedError],
) -> None:
    """Alias tables: INSERT OR IGNORE keyed by alias (UNIQUE). Append-only."""
    table_report = TableReport()

    for row in rows:
        alias_val = row.get("alias")
        incoming = _build_incoming(
            row=row,
            table=table,
            col_types=col_types,
            fk_map=fk_map,
            conn=conn,
            errors=errors,
            seed_key=alias_val,  # type: ignore[arg-type]
        )
        if incoming is None:
            continue

        # Alias rows always have source = 'seed' from the CSV
        cols = list(incoming.keys())
        vals = list(incoming.values())
        placeholders = ", ".join("?" for _ in cols)
        col_str = ", ".join(cols)
        try:
            cur = conn.execute(
                f"INSERT OR IGNORE INTO {table.table_name} ({col_str}) VALUES ({placeholders})",
                vals,
            )
            if cur.rowcount == 1:
                table_report.inserted += 1
            else:
                table_report.unchanged += 1
        except sqlite3.IntegrityError as exc:
            errors.append(
                SeedError(
                    table=table.table_name,
                    seed_key=alias_val,
                    message=f"Alias INSERT failed: {exc}",
                    exception=str(exc),
                )
            )

    report.per_table[table.table_name] = table_report
