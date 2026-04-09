# Equipment Seed Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a seed loader that reads CSV files from the repo and populates the equipment database, with hash-based change detection to never overwrite user edits.

**Architecture:** Python module `nightcrate.seed_loader` with: hash function (SHA-256 contract v1), seedable table registry (28 tables in dependency order), CSV reader with FK seed_key resolution, core loader with first-run/update modes, and CLI. Runs in a single SQLite transaction. Integrated into app startup.

**Tech Stack:** Python 3.14, aiosqlite (async for app startup) + sqlite3 (sync for CLI), hashlib SHA-256, csv stdlib, pytest

---

## File Structure

### Backend (create)
- `backend/src/nightcrate/seed_loader/__init__.py` — public API: `load_all`, `SeedReport`, types
- `backend/src/nightcrate/seed_loader/hash.py` — `compute_seed_hash` with contract v1
- `backend/src/nightcrate/seed_loader/registry.py` — `SeedableTable` dataclass + full registry + `LOAD_ORDER`
- `backend/src/nightcrate/seed_loader/csv_reader.py` — CSV parsing, header validation, FK column detection
- `backend/src/nightcrate/seed_loader/loader.py` — core: mode detection, per-table loading, re-seed logic, junction/child handling
- `backend/src/nightcrate/seed_loader/__main__.py` — CLI entry point
- `backend/src/nightcrate/data/seed/*.csv` — seed CSV files (header-only stubs initially)
- `backend/tests/test_seed_hash.py` — hash function tests
- `backend/tests/test_seed_loader.py` — integration tests for all seed/re-seed scenarios

### Backend (modify)
- `backend/src/nightcrate/main.py` — call seed loader on startup after migrations

---

### Task 1: Hash Function

**Files:**
- Create: `backend/src/nightcrate/seed_loader/__init__.py`
- Create: `backend/src/nightcrate/seed_loader/hash.py`
- Create: `backend/tests/test_seed_hash.py`

This is the most critical component — once released, the hash format is a versioned contract.

- [ ] **Step 1: Create package init**

Create `backend/src/nightcrate/seed_loader/__init__.py`:

```python
"""Equipment seed loader — populates the database from CSV seed files."""
```

- [ ] **Step 2: Implement compute_seed_hash**

Create `backend/src/nightcrate/seed_loader/hash.py`:

```python
"""Deterministic seed hash — contract version 1.

Once released, any change to the serialization format invalidates every
existing seed_hash in every user's database. Treat this as a versioned
contract. Bump HASH_CONTRACT_VERSION and provide a migration path if
the format ever changes.
"""

import hashlib
from typing import Any

HASH_CONTRACT_VERSION = "1"

# Field name regex: [a-zA-Z_][a-zA-Z0-9_]*
_FIELD_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def compute_seed_hash(fields: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of the given field dictionary.

    Returns a lowercase hex-encoded string.

    Serialization rules:
    - Keys sorted alphabetically
    - Each key emits one line: key=<encoded_value>
    - Lines joined with \\n
    - Encoded as UTF-8, then SHA-256

    Value encoding:
    - None → \\0NULL\\0
    - bool → "1" or "0"
    - int → str(value)
    - float → repr(value); NaN and infinity are forbidden
    - str → as-is; newlines in values are forbidden
    - bytes → forbidden
    """
    lines = []
    for key in sorted(fields.keys()):
        _validate_field_name(key)
        value = fields[key]
        encoded = _encode_value(value)
        lines.append(f"{key}={encoded}")
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_field_name(name: str) -> None:
    if not name:
        raise ValueError("Empty field name")
    if name[0].isdigit():
        raise ValueError(f"Field name starts with digit: {name!r}")
    if not all(c in _FIELD_NAME_CHARS for c in name):
        raise ValueError(f"Invalid characters in field name: {name!r}")


def _encode_value(value: Any) -> str:
    if value is None:
        return "\x00NULL\x00"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        import math
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"NaN and infinity are forbidden in seed hash: {value!r}")
        return repr(value)
    if isinstance(value, str):
        if "\n" in value:
            raise ValueError(f"Newlines are forbidden in seed hash string values: {value!r}")
        return value
    if isinstance(value, bytes):
        raise ValueError("bytes values are forbidden in seed hash")
    raise TypeError(f"Unsupported type for seed hash: {type(value).__name__}")
```

- [ ] **Step 3: Write hash tests**

Create `backend/tests/test_seed_hash.py`:

```python
"""Tests for the seed hash contract (version 1)."""

import pytest

from nightcrate.seed_loader.hash import HASH_CONTRACT_VERSION, compute_seed_hash


class TestHashContractVersion:
    def test_version_is_1(self):
        assert HASH_CONTRACT_VERSION == "1"


class TestValueEncoding:
    def test_none_value(self):
        h1 = compute_seed_hash({"x": None})
        h2 = compute_seed_hash({"x": "some_string"})
        assert h1 != h2  # None has distinct encoding

    def test_bool_true(self):
        h_bool = compute_seed_hash({"x": True})
        h_int = compute_seed_hash({"x": 1})
        # bool True encodes as "1", int 1 encodes as "1" — same hash
        assert h_bool == h_int

    def test_bool_false(self):
        h_bool = compute_seed_hash({"x": False})
        h_int = compute_seed_hash({"x": 0})
        assert h_bool == h_int

    def test_int_encoding(self):
        h = compute_seed_hash({"count": 42})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_float_encoding(self):
        h = compute_seed_hash({"price": 3.76})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_string_encoding(self):
        h = compute_seed_hash({"name": "ZWO ASI2600MM Pro"})
        assert isinstance(h, str)

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="NaN"):
            compute_seed_hash({"x": float("nan")})

    def test_infinity_rejected(self):
        with pytest.raises(ValueError, match="infinity"):
            compute_seed_hash({"x": float("inf")})

    def test_bytes_rejected(self):
        with pytest.raises(ValueError, match="bytes"):
            compute_seed_hash({"x": b"data"})

    def test_newline_in_string_rejected(self):
        with pytest.raises(ValueError, match="Newlines"):
            compute_seed_hash({"x": "line1\nline2"})


class TestKeyOrdering:
    def test_order_independent(self):
        h1 = compute_seed_hash({"a": 1, "b": 2, "c": 3})
        h2 = compute_seed_hash({"c": 3, "a": 1, "b": 2})
        assert h1 == h2

    def test_different_keys_different_hash(self):
        h1 = compute_seed_hash({"a": 1})
        h2 = compute_seed_hash({"b": 1})
        assert h1 != h2


class TestDeterminism:
    def test_same_input_same_hash(self):
        fields = {"name": "ZWO", "website": "https://zwoastro.com", "notes": None}
        assert compute_seed_hash(fields) == compute_seed_hash(fields)

    def test_canonical_known_value(self):
        """Pin a known hash value to detect accidental contract changes."""
        fields = {"model_name": "ASI2600MM Pro", "cooled": True, "weight_g": 700.0}
        h = compute_seed_hash(fields)
        # This value is computed once and pinned. If this test fails,
        # the hash contract has been broken.
        assert h == compute_seed_hash(fields)  # At minimum, deterministic
        # Store the actual value after first run, then pin it:
        # assert h == "<pinned_hex_value>"


class TestFieldNameValidation:
    def test_valid_names(self):
        compute_seed_hash({"model_name": "x", "pixel_size_um": 1.0})

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="Empty"):
            compute_seed_hash({"": "x"})

    def test_digit_start_rejected(self):
        with pytest.raises(ValueError, match="digit"):
            compute_seed_hash({"2fast": "x"})

    def test_special_chars_rejected(self):
        with pytest.raises(ValueError, match="Invalid"):
            compute_seed_hash({"model-name": "x"})
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_seed_hash.py -v`

- [ ] **Step 5: Pin the canonical hash value**

After tests pass, run:
```bash
uv run python -c "
from nightcrate.seed_loader.hash import compute_seed_hash
fields = {'model_name': 'ASI2600MM Pro', 'cooled': True, 'weight_g': 700.0}
print(compute_seed_hash(fields))
"
```

Update the `test_canonical_known_value` test to pin this exact hex string.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check src/nightcrate/seed_loader/ tests/test_seed_hash.py && uv run ruff format src/nightcrate/seed_loader/ tests/test_seed_hash.py
git add backend/src/nightcrate/seed_loader/__init__.py backend/src/nightcrate/seed_loader/hash.py backend/tests/test_seed_hash.py
git commit -m "feat: seed hash function (contract v1)"
```

---

### Task 2: Seedable Table Registry

**Files:**
- Create: `backend/src/nightcrate/seed_loader/registry.py`

- [ ] **Step 1: Create the registry module**

Define the `SeedableTable` dataclass and the complete registry for all 28 seedable tables in dependency load order.

```python
"""Seedable table registry — declares every table the seed loader manages."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeedableTable:
    """Declaration of a single seedable table."""
    table_name: str
    csv_filename: str
    seeded_fields: tuple[str, ...]
    fk_columns: dict[str, str] = field(default_factory=dict)
    parent_key_column: str | None = None
    is_junction: bool = False
    junction_parent: str | None = None
    junction_key_columns: tuple[str, ...] = ()
```

Then define every table entry. Here are all 28 with their exact seeded_fields (matching DB column names after FK resolution) and fk_columns (CSV column → referenced table):

**Lookup tables (7):** manufacturer, optical_design, mount_type, connection_interface, connector_size, filter_size, computer_type. Each has seeded_fields matching their non-system columns (name, description/notes, etc.) and no FK columns.

**Equipment tables (12):** sensor, camera, telescope, filter, mount, focuser, filter_wheel, oag, guide_scope, computer, software. Each has seeded_fields for all data columns and fk_columns mapping `*_seed_key` CSV columns to referenced tables.

**Child tables (2):** telescope_configuration (parent_key_column='telescope_seed_key'), filter_passband (parent_key_column='filter_seed_key').

**Junction tables (5):** camera_interface, telescope_connector, mount_interface, focuser_interface, filter_wheel_interface. Each has is_junction=True, junction_parent set, junction_key_columns set.

**Alias tables (3):** camera_alias, telescope_alias, filter_alias. These reference equipment tables via seed_key.

Then define `LOAD_ORDER: list[SeedableTable]` with all 28 entries in the exact dependency order from the spec (§6):
1. manufacturer, 2. optical_design, 3. mount_type, 4. connection_interface, 5. connector_size, 6. filter_size, 7. computer_type, 8. sensor, 9. camera, 10. camera_interface, 11. telescope, 12. telescope_connector, 13. telescope_configuration, 14. filter, 15. filter_passband, 16. mount, 17. mount_interface, 18. focuser, 19. focuser_interface, 20. filter_wheel, 21. filter_wheel_interface, 22. oag, 23. guide_scope, 24. computer, 25. software, 26. camera_alias, 27. telescope_alias, 28. filter_alias.

The implementer must read `DB_SCHEMA_DDL.sql` to get the exact column names for each table's seeded_fields. Seeded fields exclude: `id`, `created_at`, `updated_at`, `source`, `seed_key`, `seed_hash`, `active`.

For alias tables, seeded_fields include: the FK column (e.g., `camera_id`), `alias`, `source`, `confirmed`. The fk_columns map `camera_seed_key` → `camera` (etc.).

- [ ] **Step 2: Verify registry imports**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run python -c "from nightcrate.seed_loader.registry import LOAD_ORDER; print(f'{len(LOAD_ORDER)} tables registered')"`

Expected: `28 tables registered`

- [ ] **Step 3: Lint and commit**

```bash
uv run ruff check src/nightcrate/seed_loader/registry.py && uv run ruff format src/nightcrate/seed_loader/registry.py
git add backend/src/nightcrate/seed_loader/registry.py
git commit -m "feat: seedable table registry (28 tables in dependency order)"
```

---

### Task 3: CSV Reader

**Files:**
- Create: `backend/src/nightcrate/seed_loader/csv_reader.py`

- [ ] **Step 1: Implement CSV reader**

```python
"""CSV reader for seed data files."""

import csv
from pathlib import Path
from typing import Any

from nightcrate.seed_loader.registry import SeedableTable


def read_seed_csv(
    csv_path: Path,
    table: SeedableTable,
) -> list[dict[str, Any]]:
    """Read a seed CSV file and return a list of typed row dictionaries.

    - Validates header columns against the table's expected columns
    - Skips comment lines (starting with #)
    - Converts empty strings to None
    - Converts boolean fields (0/1) to int
    - Converts numeric fields to int/float where appropriate
    - Returns raw rows with CSV column names (FK seed_keys not yet resolved)
    """
```

The reader should:
1. Open the CSV file (UTF-8)
2. Filter out comment lines (lines starting with `#`)
3. Parse with `csv.DictReader`
4. Validate that the header contains `seed_key` as first column (unless junction table)
5. Validate that all expected columns are present (seeded_fields mapped back through fk_columns, plus `seed_key`)
6. For each row, convert empty strings to `None`
7. Return list of dicts with string keys and `str | None` values

Type conversion happens later in the loader (not in the reader) since the reader doesn't know column types. The reader just handles CSV parsing and validation.

- [ ] **Step 2: Lint and commit**

```bash
git add backend/src/nightcrate/seed_loader/csv_reader.py
git commit -m "feat: CSV reader for seed data files"
```

---

### Task 4: Core Loader

**Files:**
- Create: `backend/src/nightcrate/seed_loader/loader.py`

This is the largest and most complex component. It implements:
- Mode detection (first_run vs update)
- FK resolution via in-memory seed_key → id map
- Per-table loading with re-seed decision logic
- Junction table handling (delete-and-reinsert for updated parents)
- Parent/child coherence (skip children if parent is user-modified)
- Error collection and transaction semantics
- SeedReport generation

- [ ] **Step 1: Define report types**

In `backend/src/nightcrate/seed_loader/__init__.py`, add the report dataclasses:

```python
"""Equipment seed loader — populates the database from CSV seed files."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class TableReport:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_user_modified: list[str] = field(default_factory=list)
    skipped_corrupt: list[str] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)


@dataclass
class SeedError:
    table: str
    seed_key: str | None
    message: str
    exception: str | None = None


@dataclass
class SeedReport:
    mode: Literal["first_run", "update"]
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    per_table: dict[str, TableReport] = field(default_factory=dict)
    errors: list[SeedError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0
```

- [ ] **Step 2: Implement the core loader**

Create `backend/src/nightcrate/seed_loader/loader.py` with:

```python
"""Core seed loader — loads CSV seed data into the equipment database."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from nightcrate.seed_loader import SeedError, SeedReport, TableReport
from nightcrate.seed_loader.csv_reader import read_seed_csv
from nightcrate.seed_loader.hash import HASH_CONTRACT_VERSION, compute_seed_hash
from nightcrate.seed_loader.registry import LOAD_ORDER, SeedableTable


def load_all(
    conn: sqlite3.Connection,
    csv_root: Path,
    mode: Literal["first_run", "update", "auto"] = "auto",
) -> SeedReport:
    """Load all seed data from CSV files into the database.

    Runs the entire operation in a single transaction. If any error occurs,
    everything rolls back — there is no partial seed state.
    """
```

Key implementation details:

**Mode detection:** Query `seed_loader_meta` for `first_seeded_at`. If present, mode is `update`. If absent, mode is `first_run`.

**Hash contract check:** On update mode, verify stored `hash_contract_version` matches `HASH_CONTRACT_VERSION`. Refuse to run on mismatch.

**In-memory FK map:** `dict[tuple[str, str], int]` mapping `(table_name, seed_key)` → row `id`. Populated as rows are inserted. Used by FK resolution.

**Per-table loading (non-junction, non-child):**
1. Read CSV rows via `read_seed_csv`
2. For each row, resolve FK seed_keys to integer IDs via the map
3. Build the field dict (seeded_fields only)
4. In first_run mode: INSERT with source='seed', seed_key, seed_hash
5. In update mode: apply re-seed decision logic (§9 of spec)
6. Add `(table_name, seed_key) → id` to the FK map

**Junction table loading:**
1. Read CSV rows
2. For each row, resolve FK seed_keys
3. Only process rows whose parent was INSERTED or UPDATED in this run
4. For those parents: DELETE existing junction rows, INSERT new ones
5. Skip junction rows for unchanged/user-modified parents

**Child table loading (telescope_configuration, filter_passband):**
1. Read CSV rows
2. Group by parent seed_key
3. For each parent that was INSERTED: insert all children
4. For each parent that was UPDATED (unmodified): delete unmodified seed children, reinsert from CSV. Preserve user-modified children (hash mismatch) and user-created children (source='user').
5. For each parent that was SKIPPED_USER_MODIFIED: skip all children

**Orphan detection:** After processing all CSV rows for a table, query for rows with `source='seed'` whose `seed_key` is not in the CSV. Report as ORPHANED_SEED.

**seed_loader_meta updates:** On first_run, insert `hash_contract_version`, `first_seeded_at`, `last_seeded_at`. On update, update `last_seeded_at`.

**Transaction:** The caller wraps in a transaction. The loader raises on error, letting the transaction roll back.

- [ ] **Step 3: Export load_all from __init__**

Update `backend/src/nightcrate/seed_loader/__init__.py` to export `load_all`:

```python
from nightcrate.seed_loader.loader import load_all

__all__ = ["load_all", "SeedReport", "SeedError", "TableReport"]
```

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check src/nightcrate/seed_loader/ && uv run ruff format src/nightcrate/seed_loader/
git add backend/src/nightcrate/seed_loader/
git commit -m "feat: core seed loader with re-seed decision logic"
```

---

### Task 5: CLI Entry Point

**Files:**
- Create: `backend/src/nightcrate/seed_loader/__main__.py`

- [ ] **Step 1: Implement CLI**

```python
"""CLI entry point for the seed loader.

Usage:
    python -m nightcrate.seed_loader --db nightcrate.sqlite --csv-root path/to/seed
    python -m nightcrate.seed_loader --db nightcrate.sqlite --csv-root path/to/seed --update
    python -m nightcrate.seed_loader --db nightcrate.sqlite --csv-root path/to/seed --dry-run
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from nightcrate.seed_loader import SeedReport, load_all


def main() -> int:
    parser = argparse.ArgumentParser(description="NightCrate equipment seed loader")
    parser.add_argument("--db", required=True, type=Path, help="Path to SQLite database")
    parser.add_argument("--csv-root", required=True, type=Path, help="Path to seed CSV directory")
    parser.add_argument("--update", action="store_true", help="Force update mode")
    parser.add_argument("--first-run", action="store_true", help="Force first-run mode")
    parser.add_argument("--dry-run", action="store_true", help="Compute report but roll back")
    parser.add_argument("--verbose", action="store_true", help="Log per-row decisions")
    parser.add_argument("--json", action="store_true", help="Output report as JSON")
    args = parser.parse_args()

    if args.update and args.first_run:
        print("Error: --update and --first-run are mutually exclusive", file=sys.stderr)
        return 2

    mode = "auto"
    if args.update:
        mode = "update"
    elif args.first_run:
        mode = "first_run"

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        report = load_all(conn, args.csv_root, mode=mode)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    _print_report(report, json_mode=args.json, verbose=args.verbose)
    return 0 if report.ok else 1


def _print_report(report: SeedReport, json_mode: bool, verbose: bool) -> None:
    # Format and print the report (human-readable or JSON)
    if json_mode:
        # Serialize SeedReport to JSON
        import dataclasses
        data = dataclasses.asdict(report)
        # Convert datetime objects to ISO strings
        data["started_at"] = report.started_at.isoformat()
        data["finished_at"] = report.finished_at.isoformat() if report.finished_at else None
        print(json.dumps(data, indent=2))
    else:
        print(f"Seed loader: {report.mode} mode")
        for table_name, tr in report.per_table.items():
            parts = []
            if tr.inserted:
                parts.append(f"{tr.inserted} inserted")
            if tr.updated:
                parts.append(f"{tr.updated} updated")
            if tr.unchanged:
                parts.append(f"{tr.unchanged} unchanged")
            if tr.skipped_user_modified:
                parts.append(f"{len(tr.skipped_user_modified)} user-modified")
            if tr.orphaned:
                parts.append(f"{len(tr.orphaned)} orphaned")
            if parts:
                print(f"  {table_name}: {', '.join(parts)}")
        if report.errors:
            print(f"\n{len(report.errors)} errors:")
            for err in report.errors:
                print(f"  [{err.table}] {err.seed_key}: {err.message}")
        elif report.ok:
            total_inserted = sum(t.inserted for t in report.per_table.values())
            total_updated = sum(t.updated for t in report.per_table.values())
            print(f"\nOK — {total_inserted} inserted, {total_updated} updated")


if __name__ == "__main__":
    sys.exit(main())
```

Exit codes: 0 = success, 1 = errors, 2 = CLI usage error, 3 = hash contract mismatch.

- [ ] **Step 2: Lint and commit**

```bash
git add backend/src/nightcrate/seed_loader/__main__.py
git commit -m "feat: seed loader CLI entry point"
```

---

### Task 6: Stub CSV Files

**Files:**
- Create: `backend/src/nightcrate/data/seed/*.csv` (28 files, header-only stubs)

- [ ] **Step 1: Create all CSV stub files**

Create the `backend/src/nightcrate/data/seed/` directory and 28 CSV files, each containing only the header row. The headers must match exactly what the CSV reader expects.

For each table, the CSV header is: `seed_key` + the seeded fields with FK columns replaced by `*_seed_key` names.

Examples:
- `manufacturer.csv`: `seed_key,name,website,notes`
- `sensor.csv`: `seed_key,manufacturer_seed_key,model_name,sensor_type,pixel_size_um,resolution_x,resolution_y,sensor_width_mm,sensor_height_mm,adc_bit_depth,full_well_capacity_ke,read_noise_e,peak_qe_pct,bayer_pattern,dual_gain,hcg_threshold_gain,notes`
- `camera.csv`: `seed_key,manufacturer_seed_key,sensor_seed_key,connector_size_seed_key,model_name,cooled,cooling_delta_c,back_focus_mm,weight_g,tilt_adapter,has_usb_hub,usb_hub_interface_seed_key,unity_gain,notes`
- `camera_interface.csv`: `camera_seed_key,interface_seed_key` (no seed_key column — junction table)
- `telescope_configuration.csv`: `seed_key,telescope_seed_key,config_name,accessory_name,reduction_factor,effective_focal_length_mm,effective_focal_ratio,effective_image_circle_mm,effective_back_focus_mm,is_native,notes`

The implementer must derive headers from the registry's `seeded_fields` and `fk_columns` for each table. Read `DB_SCHEMA_DDL.sql` for exact column names.

- [ ] **Step 2: Verify all 28 files exist**

Run: `ls backend/src/nightcrate/data/seed/*.csv | wc -l`

Expected: `28`

- [ ] **Step 3: Commit**

```bash
git add backend/src/nightcrate/data/seed/
git commit -m "feat: stub CSV seed files (headers only, 28 tables)"
```

---

### Task 7: Integration Tests

**Files:**
- Create: `backend/tests/test_seed_loader.py`

- [ ] **Step 1: Write test fixtures and first-run test**

Create a test fixture that sets up an in-memory SQLite database with the full equipment schema (apply all migrations), and a temp directory with test CSV files.

Tests to write:
1. `test_first_run` — load with test CSVs containing a manufacturer + sensor + camera. Verify all rows present in DB with correct source='seed', seed_key, and seed_hash.
2. `test_first_run_sets_meta` — verify seed_loader_meta has hash_contract_version, first_seeded_at, last_seeded_at.
3. `test_reseed_unchanged` — run first_run, then run again with identical CSVs. All rows should be UNCHANGED.
4. `test_reseed_user_modified` — run first_run, directly UPDATE a row in the DB (changing a seeded field), re-run. That row should be SKIPPED_USER_MODIFIED.
5. `test_reseed_csv_changed` — run first_run, modify the CSV (change a field value), re-run on unmodified DB. Row should be UPDATED with new hash.
6. `test_parent_child` — seed a telescope + configuration. Verify config loaded. Re-seed with changed config, verify updated.
7. `test_parent_child_user_modified_parent` — modify telescope in DB, re-seed. Telescope AND its configs should be skipped.
8. `test_junction_table` — seed a camera + camera_interface rows. Verify junction rows present. Update camera in CSV, re-seed. Junction rows should be refreshed.
9. `test_orphaned_seed` — seed a manufacturer, then re-seed without that manufacturer in CSV. Should be reported as ORPHANED_SEED, not deleted.
10. `test_fk_resolution_failure` — CSV references a seed_key that doesn't exist. Should abort with error.
11. `test_transaction_rollback` — inject an error mid-load (e.g., invalid FK). Verify no partial state in DB.

- [ ] **Step 2: Run tests**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest tests/test_seed_loader.py -v`

- [ ] **Step 3: Lint and commit**

```bash
git add backend/tests/test_seed_loader.py
git commit -m "test: comprehensive seed loader integration tests"
```

---

### Task 8: App Startup Integration

**Files:**
- Modify: `backend/src/nightcrate/main.py`

- [ ] **Step 1: Call seed loader on startup**

In the FastAPI lifespan function, after `apply_migrations()`, add seed loading:

```python
# Apply seed data (first run or check for updates)
try:
    from nightcrate.seed_loader import load_all
    from nightcrate.seed_loader.registry import LOAD_ORDER
    import importlib.resources

    csv_root = importlib.resources.files("nightcrate") / "data" / "seed"
    async with get_db() as conn:
        # load_all expects a sync sqlite3.Connection, but we have aiosqlite.
        # Use the underlying sync connection for the seed loader.
        report = load_all(conn._conn, csv_root, mode="auto")
        if not report.ok:
            import logging
            logger = logging.getLogger("nightcrate")
            for err in report.errors:
                logger.warning("Seed loader error [%s] %s: %s", err.table, err.seed_key, err.message)
        await conn.commit()
except Exception:
    import logging
    logging.getLogger("nightcrate").warning("Seed loader failed", exc_info=True)
    # Non-fatal — don't block startup
```

Note: The seed loader uses sync `sqlite3.Connection` but the app uses `aiosqlite`. Access the underlying sync connection via `conn._conn`. This is an implementation detail of aiosqlite but is the standard workaround for sync code that needs to run inside an async context. Alternatively, wrap `load_all` in `asyncio.to_thread()`.

Actually — the cleaner approach is to use `asyncio.to_thread` to run the sync loader:

```python
import asyncio
report = await asyncio.to_thread(load_all, conn._conn, csv_root, "auto")
```

- [ ] **Step 2: Verify app starts**

Run: `cd /Users/fbaptiste/dev/nightcrate && make backend`

The app should start without errors. The seed loader should run in first_run mode and report 0 inserts (since CSVs are header-only stubs).

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v`

All tests should pass.

- [ ] **Step 4: Lint and commit**

```bash
git add backend/src/nightcrate/main.py
git commit -m "feat: seed loader runs on app startup after migrations"
```

---

### Task 9: Full Backend Checks

**Files:** None (verification only)

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/fbaptiste/dev/nightcrate/backend && uv run pytest -v`

- [ ] **Step 2: Lint and format**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`

- [ ] **Step 3: Security scan**

Run: `uv run bandit -r src/`

- [ ] **Step 4: Frontend build**

Run: `cd /Users/fbaptiste/dev/nightcrate/frontend && npm run build`

- [ ] **Step 5: CLI smoke test**

Run the seed loader CLI against the app database:
```bash
cd /Users/fbaptiste/dev/nightcrate/backend
uv run python -m nightcrate.seed_loader \
  --db "$HOME/Library/Application Support/NightCrate/nightcrate.db" \
  --csv-root src/nightcrate/data/seed \
  --dry-run --verbose
```

Should print a report showing 0 rows processed (header-only CSVs).
