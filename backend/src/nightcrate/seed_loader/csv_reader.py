"""
CSV reader for seed data files.

Parses seed CSVs with header validation, comment line filtering, and
FK seed_key column detection.
"""

import csv
import io
from pathlib import Path

from nightcrate.seed_loader.registry import SeedableTable

# Alias table names — these have no seed_key column; identified by alias text.
_ALIAS_TABLE_SUFFIX = "_alias"


def read_seed_csv(csv_path: Path, table: SeedableTable) -> list[dict[str, str | None]]:
    """Read a seed CSV file and return a list of row dictionaries.

    - UTF-8 encoding, RFC 4180 format
    - Lines starting with # are comments (skipped)
    - First row is header
    - Validates header against expected columns for the table
    - Empty cells become None
    - Returns list of dicts with string keys and str|None values
    - Type conversion happens later in the loader, not here
    """
    raw = csv_path.read_text(encoding="utf-8")

    # Filter comment lines (strip leading whitespace before checking #)
    lines = [line for line in raw.splitlines(keepends=True) if not line.lstrip().startswith("#")]

    reader = csv.DictReader(io.StringIO("".join(lines)))

    _validate_header(reader.fieldnames, table)

    rows = []
    for row in reader:
        rows.append({k: (v if v != "" else None) for k, v in row.items()})

    return rows


def _has_seed_key(table: SeedableTable) -> bool:
    """Return True if this table has a seed_key column.

    Alias tables are identified by the alias text (UNIQUE constraint on alias)
    and have no seed_key / seed_hash columns. Junction tables also have no
    seed_key column.
    """
    if table.is_junction:
        return False
    if table.table_name.endswith(_ALIAS_TABLE_SUFFIX):
        return False
    return True


def _expected_columns(table: SeedableTable) -> set[str]:
    """Compute the expected CSV column names for a table."""
    if table.is_junction:
        # Junction tables: only the FK seed_key columns
        return set(table.fk_columns.keys())

    # Build a mapping from DB FK column name → CSV seed_key column name.
    # Convention: "manufacturer_seed_key" (csv) → "manufacturer_id" (db).
    # This holds for all FK columns including non-standard prefixes because
    # we strip "_seed_key" and append "_id".
    fk_db_col_to_csv_col: dict[str, str] = {}
    for csv_col in table.fk_columns:
        db_col = csv_col.replace("_seed_key", "_id")
        fk_db_col_to_csv_col[db_col] = csv_col

    cols: set[str] = set()

    if _has_seed_key(table):
        cols.add("seed_key")

    for field in table.seeded_fields:
        if field in fk_db_col_to_csv_col:
            # Replace DB FK column name with its CSV seed_key equivalent
            cols.add(fk_db_col_to_csv_col[field])
        else:
            cols.add(field)

    # Child tables need the parent FK column in the CSV
    if table.parent_key_column:
        cols.add(table.parent_key_column)

    return cols


def _validate_header(fieldnames: list[str] | None, table: SeedableTable) -> None:
    if not fieldnames:
        raise ValueError(f"CSV for {table.table_name} has no header row")

    actual = set(fieldnames)
    expected = _expected_columns(table)

    missing = expected - actual
    extra = actual - expected

    if missing:
        raise ValueError(f"CSV for {table.table_name} missing columns: {sorted(missing)}")
    if extra:
        raise ValueError(f"CSV for {table.table_name} has unexpected columns: {sorted(extra)}")
