"""One-shot re-hash steps for migrations that change a table's ``seeded_fields``.

A field's NAME is part of the hashed payload, so renaming or adding a seeded field
invalidates the stored hash of every row in that table at once. The loader has an
ordinary repair for that — if a row still hashes to the CSV's own value then nobody
edited it, so the hash is rewritten in place. But that test conflates two different
questions, *was this row edited* and *is this row up to date*, and they come apart
whenever the same release also changes CSV values for some of those rows: an
untouched-but-stale row then looks exactly like an edited one and is stranded.

A step here answers the sharper question directly. It reconstructs what the row's
hash **was** under the old field names, from values still present under the new
ones, and compares that to what is stored. A match means the row was untouched at
the moment the migration ran — whatever the CSV says now — so the hash is rewritten
and the normal update path carries the CSV forward from there. A mismatch is a real
user edit and is left alone.

Steps run once per database, recorded by key in ``seed_loader_meta``. They are
history: the old field tuples below describe the schema as it was and must never be
"updated" to match the present one.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from nightcrate.seed_loader.hash import compute_seed_hash
from nightcrate.seed_loader.registry import REGISTRY


@dataclass(frozen=True)
class RehashStep:
    """Recovers the pre-migration hash of one table's rows."""

    key: str
    table: str
    recover: Callable[[sqlite3.Row], dict]


# --- 0052.read_noise_by_gain -------------------------------------------------
# sensor.read_noise_e became read_noise_low_gain_e, with a new
# read_noise_high_gain_e beside it, and the migration moved each row's value into
# whichever column describes it. Exactly one of the two is populated on every
# seeded row, so the original single value is recoverable.

_SENSOR_FIELDS_BEFORE_0052 = (
    "manufacturer_id",
    "model_name",
    "sensor_type",
    "pixel_size_um",
    "resolution_x",
    "resolution_y",
    "sensor_width_mm",
    "sensor_height_mm",
    "adc_bit_depth",
    "full_well_capacity_ke",
    "read_noise_e",
    "peak_qe_pct",
    "bayer_pattern",
    "dual_gain",
    "notes",
    "source_url",
)

# camera's two columns were renamed and nothing moved, so the mapping is direct.
_CAMERA_RENAMES_0052 = {
    "effective_read_noise_lcg_e": "effective_read_noise_low_gain_e",
    "effective_read_noise_hcg_e": "effective_read_noise_high_gain_e",
}


def _sensor_before_0052(row: sqlite3.Row) -> dict:
    fields = {f: row[f] for f in _SENSOR_FIELDS_BEFORE_0052 if f != "read_noise_e"}
    low = row["read_noise_low_gain_e"]
    fields["read_noise_e"] = low if low is not None else row["read_noise_high_gain_e"]
    return fields


def _camera_before_0052(row: sqlite3.Row) -> dict:
    # 0052 renamed two columns and changed nothing else on camera, so the field
    # set is today's with those two keys spelled the old way.
    old_name = {new: old for old, new in _CAMERA_RENAMES_0052.items()}
    return {old_name.get(f, f): row[f] for f in REGISTRY["camera"].seeded_fields}


# --- 0053.mount_payload_convention -------------------------------------------
# payload_capacity_with_cw_kg was added to mount's seeded_fields. Nothing was
# renamed and no value moved, so the old field set is simply today's without it.

_MOUNT_FIELD_ADDED_0053 = "payload_capacity_with_cw_kg"


def _mount_before_0053(row: sqlite3.Row) -> dict:
    return {f: row[f] for f in REGISTRY["mount"].seeded_fields if f != _MOUNT_FIELD_ADDED_0053}


# --- 0054.sensor_peak_qe_band ------------------------------------------------
# peak_qe_wavelength_nm was added to sensor's seeded_fields. A database that
# predates 0052 is already carried by that step, which re-hashes with today's
# field set; this one covers a database seeded between the two migrations.

_SENSOR_FIELD_ADDED_0054 = "peak_qe_wavelength_nm"


def _sensor_before_0054(row: sqlite3.Row) -> dict:
    return {f: row[f] for f in REGISTRY["sensor"].seeded_fields if f != _SENSOR_FIELD_ADDED_0054}


REHASH_STEPS: tuple[RehashStep, ...] = (
    RehashStep("rehash.0052.sensor", "sensor", _sensor_before_0052),
    RehashStep("rehash.0052.camera", "camera", _camera_before_0052),
    RehashStep("rehash.0053.mount", "mount", _mount_before_0053),
    RehashStep("rehash.0054.sensor", "sensor", _sensor_before_0054),
)


def apply_rehash_steps(conn: sqlite3.Connection) -> dict[str, int]:
    """Run any step this database has not seen. Returns rows re-hashed per table."""
    done = {r["key"] for r in conn.execute("SELECT key FROM seed_loader_meta").fetchall()}
    counts: dict[str, int] = {}

    for step in REHASH_STEPS:
        if step.key in done:
            continue
        current_fields = REGISTRY[step.table].seeded_fields
        rows = conn.execute(
            f"SELECT * FROM {step.table} "  # nosec B608 - table name from internal allow-list
            f"WHERE source = 'seed' AND seed_hash IS NOT NULL"
        ).fetchall()

        rehashed = 0
        for row in rows:
            try:
                before = step.recover(row)
            except IndexError, KeyError:
                # The migration this step pairs with has not been applied. Leave
                # the step unmarked so it runs once the schema catches up.
                break
            if compute_seed_hash(before) != row["seed_hash"]:
                continue  # a real user edit
            conn.execute(
                f"UPDATE {step.table} SET seed_hash = ? WHERE id = ?",  # nosec B608 - internal allow-list
                (compute_seed_hash({f: row[f] for f in current_fields}), row["id"]),
            )
            rehashed += 1
        else:
            conn.execute(
                "INSERT OR REPLACE INTO seed_loader_meta (key, value) VALUES (?, ?)",
                (step.key, str(rehashed)),
            )
            counts[step.table] = counts.get(step.table, 0) + rehashed

    return counts
