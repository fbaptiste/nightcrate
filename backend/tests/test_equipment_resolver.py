"""Tests for the FITS equipment resolver (services/equipment_resolver.py).

Covers the §4 normalization rules, every §6 line-name mapping, the four resolve
outcomes (resolved / resolved_retired / unresolved / ambiguous), rig-scoped
filter resolution and its fallbacks, the promotion utility, and the
caller-owns-the-transaction (no auto-commit) guarantee.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import aiosqlite
import pytest

from nightcrate.db.session import get_db_path
from nightcrate.services.equipment_resolver import (
    EquipmentResolver,
    ResolverStats,
    RigContext,
    canonicalize_line_name,
    confirm_unresolved_observation,
    normalize_alias,
)


async def _connect() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(str(get_db_path()))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture
async def equipment():
    """Build a small equipment graph and yield (connection, id-map)."""
    conn = await _connect()
    ids: dict[str, int] = {}

    cur = await conn.execute("INSERT INTO manufacturer (name) VALUES ('TestCo')")
    ids["mfr"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO sensor (manufacturer_id, model_name, sensor_type, pixel_size_um, "
        "resolution_x, resolution_y) VALUES (?, 'IMX571', 'mono', 3.76, 6248, 4176)",
        (ids["mfr"],),
    )
    ids["sensor"] = cur.lastrowid

    # Cameras — one active, one retired.
    cur = await conn.execute(
        "INSERT INTO camera (manufacturer_id, sensor_id, model_name) VALUES (?, ?, 'Mono Cam A')",
        (ids["mfr"], ids["sensor"]),
    )
    ids["cam_active"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO camera (manufacturer_id, sensor_id, model_name, active) "
        "VALUES (?, ?, 'Old Cam', 0)",
        (ids["mfr"], ids["sensor"]),
    )
    ids["cam_retired"] = cur.lastrowid
    await conn.execute(
        "INSERT INTO camera_alias (camera_id, alias, source, confirmed) "
        "VALUES (?, 'zwo asi2600mm pro', 'user', 1)",
        (ids["cam_active"],),
    )
    await conn.execute(
        "INSERT INTO camera_alias (camera_id, alias, source, confirmed) "
        "VALUES (?, 'old camera', 'user', 1)",
        (ids["cam_retired"],),
    )

    # Telescope + native config + alias.
    cur = await conn.execute(
        "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) "
        "VALUES (?, 'Scope X', 280)",
        (ids["mfr"],),
    )
    ids["tele"] = cur.lastrowid
    cur = await conn.execute(
        "INSERT INTO telescope_configuration (telescope_id, config_name, "
        "effective_focal_length_mm, effective_focal_ratio, is_native) "
        "VALUES (?, 'Native', 2800, 10, 1)",
        (ids["tele"],),
    )
    ids["tele_config"] = cur.lastrowid
    await conn.execute(
        "INSERT INTO telescope_alias (telescope_id, alias, source, confirmed) "
        "VALUES (?, 'scope x', 'user', 1)",
        (ids["tele"],),
    )

    # Filters: two Ha (7nm + 3nm) and one Oiii, each with a passband.
    cur = await conn.execute("INSERT INTO filter_type (name) VALUES ('Narrowband')")
    ids["ftype"] = cur.lastrowid
    for key, model in [
        ("ha7", "Optolong Ha 7nm"),
        ("ha3", "Antlia Ha 3nm"),
        ("oiii", "Optolong Oiii 3nm"),
    ]:
        cur = await conn.execute(
            "INSERT INTO filter (manufacturer_id, filter_type_id, model_name) VALUES (?, ?, ?)",
            (ids["mfr"], ids["ftype"], model),
        )
        ids[key] = cur.lastrowid
    for key, line, cw, bw in [
        ("ha7", "Ha", 656.3, 7),
        ("ha3", "Ha", 656.3, 3),
        ("oiii", "Oiii", 500.7, 3),
    ]:
        await conn.execute(
            "INSERT INTO filter_passband "
            "(filter_id, line_name, central_wavelength_nm, bandwidth_nm) VALUES (?, ?, ?, ?)",
            (ids[key], line, cw, bw),
        )
    # Exact-model filter alias (for the model-name resolution path).
    await conn.execute(
        "INSERT INTO filter_alias (filter_id, alias, source, confirmed) "
        "VALUES (?, 'optolong oiii 3nm', 'user', 1)",
        (ids["oiii"],),
    )

    # Rigs + slots: one with a unique Ha, one with two Ha (ambiguous), one empty.
    for key, name in [
        ("rig_unique", "Rig Unique"),
        ("rig_ambig", "Rig Ambiguous"),
        ("rig_empty", "Rig Empty"),
    ]:
        cur = await conn.execute(
            "INSERT INTO rig (name, telescope_configuration_id, camera_id) VALUES (?, ?, ?)",
            (name, ids["tele_config"], ids["cam_active"]),
        )
        ids[key] = cur.lastrowid
    await conn.execute(
        "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 1, ?)",
        (ids["rig_unique"], ids["ha7"]),
    )
    await conn.execute(
        "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 2, ?)",
        (ids["rig_unique"], ids["oiii"]),
    )
    await conn.execute(
        "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 1, ?)",
        (ids["rig_ambig"], ids["ha7"]),
    )
    await conn.execute(
        "INSERT INTO rig_filter_slot (rig_id, slot_number, filter_id) VALUES (?, 2, ?)",
        (ids["rig_ambig"], ids["ha3"]),
    )

    await conn.commit()
    yield conn, ids
    await conn.close()


async def _observation_count(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute("SELECT COUNT(*) AS n FROM unresolved_equipment_observation")
    return (await cur.fetchone())["n"]


# ── normalize_alias (§4) ─────────────────────────────────────────────────────


class TestNormalizeAlias:
    def test_strip_and_collapse_whitespace(self):
        assert normalize_alias("  ZWO   ASI2600MM   Pro  ") == "zwo asi2600mm pro"

    def test_tabs_and_newlines_collapse_to_single_space(self):
        assert normalize_alias("Lum\t\n L") == "lum l"

    def test_lowercase(self):
        assert normalize_alias("Optolong L-Pro") == "optolong l-pro"

    def test_punctuation_preserved(self):
        assert normalize_alias("7nm Ha") == "7nm ha"
        assert normalize_alias("UV/IR") == "uv/ir"
        assert normalize_alias("H-Alpha") == "h-alpha"
        assert normalize_alias("ASI (cooled)") == "asi (cooled)"

    def test_nfkc_folds_fullwidth(self):
        # Fullwidth Latin letters fold to ASCII under NFKC, then lowercase.
        assert normalize_alias("ＺＷＯ") == "zwo"

    def test_removes_control_and_zero_width_chars(self):
        assert normalize_alias("ha\x00lpha") == "halpha"
        assert normalize_alias("h​lpha") == "hlpha"
        assert normalize_alias("name﻿") == "name"

    def test_empty_and_blank(self):
        assert normalize_alias("") == ""
        assert normalize_alias("   ") == ""


# ── canonicalize_line_name (§6) ──────────────────────────────────────────────

# Independent restatement of the §6 table (every accepted spelling).
_LINE_NAME_CASES: dict[str, str] = {
    "ha": "Ha",
    "h-a": "Ha",
    "h alpha": "Ha",
    "h-alpha": "Ha",
    "halpha": "Ha",
    "hydrogen alpha": "Ha",
    "hydrogen-alpha": "Ha",
    "hb": "Hb",
    "h-b": "Hb",
    "h beta": "Hb",
    "h-beta": "Hb",
    "hbeta": "Hb",
    "hydrogen beta": "Hb",
    "oiii": "Oiii",
    "o3": "Oiii",
    "o-iii": "Oiii",
    "o iii": "Oiii",
    "oxygen iii": "Oiii",
    "oxygen-iii": "Oiii",
    "oxygeniii": "Oiii",
    "sii": "Sii",
    "s2": "Sii",
    "s-ii": "Sii",
    "s ii": "Sii",
    "sulfur ii": "Sii",
    "sulphur ii": "Sii",
    "sulfur-ii": "Sii",
    "l": "Lum",
    "lum": "Lum",
    "luminance": "Lum",
    "clear": "Lum",
    "r": "R",
    "red": "R",
    "g": "G",
    "green": "G",
    "b": "B",
    "blue": "B",
    "uvir": "UVIR",
    "uv/ir": "UVIR",
    "uv-ir": "UVIR",
    "uv ir cut": "UVIR",
}


class TestCanonicalizeLineName:
    @pytest.mark.parametrize(("spelling", "canonical"), list(_LINE_NAME_CASES.items()))
    def test_every_mapping(self, spelling: str, canonical: str):
        assert canonicalize_line_name(spelling) == canonical

    def test_case_and_whitespace_insensitive(self):
        assert canonicalize_line_name("  H-Alpha ") == "Ha"
        assert canonicalize_line_name("OXYGEN III") == "Oiii"

    def test_unknown_returns_none(self):
        assert canonicalize_line_name("Optolong L-Pro") is None
        assert canonicalize_line_name("L-eNhance") is None
        assert canonicalize_line_name("") is None


# ── Resolve outcomes (§5) ────────────────────────────────────────────────────


class TestResolveCameraTelescope:
    async def test_resolved_active(self, equipment):
        conn, ids = equipment
        resolver = EquipmentResolver(conn)
        result = await resolver.resolve_camera("ZWO ASI2600MM Pro")
        assert result.status == "resolved"
        assert result.equipment_id == ids["cam_active"]
        assert result.equipment["model_name"] == "Mono Cam A"
        assert result.newly_observed is False
        assert result.normalized_alias == "zwo asi2600mm pro"

    async def test_resolved_retired(self, equipment):
        conn, ids = equipment
        result = await EquipmentResolver(conn).resolve_camera("Old Camera")
        assert result.status == "resolved_retired"
        assert result.equipment_id == ids["cam_retired"]
        assert result.equipment["active"] == 0

    async def test_resolve_telescope(self, equipment):
        conn, ids = equipment
        result = await EquipmentResolver(conn).resolve_telescope("Scope X")
        assert result.status == "resolved"
        assert result.equipment_id == ids["tele"]

    async def test_last_seen_at_bumped_on_hit(self, equipment):
        conn, _ = equipment
        await conn.execute(
            "UPDATE camera_alias SET last_seen_at = '2000-01-01 00:00:00' "
            "WHERE alias = 'zwo asi2600mm pro'"
        )
        await EquipmentResolver(conn).resolve_camera("ZWO ASI2600MM Pro")
        cur = await conn.execute(
            "SELECT last_seen_at FROM camera_alias WHERE alias = 'zwo asi2600mm pro'"
        )
        assert (await cur.fetchone())["last_seen_at"] != "2000-01-01 00:00:00"

    async def test_unresolved_records_and_increments(self, equipment):
        conn, _ = equipment
        resolver = EquipmentResolver(conn)

        first = await resolver.resolve_camera("Brand New Cam")
        assert first.status == "unresolved"
        assert first.equipment_id is None
        assert first.newly_observed is True
        assert first.normalized_alias == "brand new cam"

        cur = await conn.execute(
            "SELECT seen_count, original_observation, source, equipment_kind "
            "FROM unresolved_equipment_observation WHERE normalized_alias = 'brand new cam'"
        )
        row = await cur.fetchone()
        assert row["seen_count"] == 1
        assert row["original_observation"] == "Brand New Cam"  # raw string preserved
        assert row["source"] == "nina"  # default
        assert row["equipment_kind"] == "camera"

        second = await resolver.resolve_camera("Brand New Cam", source="asiair")
        assert second.status == "unresolved"
        assert second.newly_observed is False
        cur = await conn.execute(
            "SELECT seen_count FROM unresolved_equipment_observation "
            "WHERE normalized_alias = 'brand new cam'"
        )
        assert (await cur.fetchone())["seen_count"] == 2

    @pytest.mark.parametrize("blank", ["", "   ", None])
    async def test_blank_is_unresolved_without_observation(self, equipment, blank):
        conn, _ = equipment
        before = await _observation_count(conn)
        result = await EquipmentResolver(conn).resolve_camera(blank)
        assert result.status == "unresolved"
        assert result.normalized_alias == ""
        assert result.newly_observed is False
        assert await _observation_count(conn) == before  # nothing recorded


# ── Filter resolution (§6) ───────────────────────────────────────────────────


class TestResolveFilter:
    async def test_exact_alias_hit(self, equipment):
        conn, ids = equipment
        result = await EquipmentResolver(conn).resolve_filter("Optolong Oiii 3nm")
        assert result.status == "resolved"
        assert result.equipment_id == ids["oiii"]

    async def test_line_name_scoped_unique(self, equipment):
        conn, ids = equipment
        ctx = RigContext(rig_id=ids["rig_unique"])
        result = await EquipmentResolver(conn).resolve_filter("Ha", rig_context=ctx)
        assert result.status == "resolved"
        assert result.equipment_id == ids["ha7"]

    async def test_line_name_canonicalization_feeds_resolution(self, equipment):
        conn, ids = equipment
        ctx = RigContext(rig_id=ids["rig_unique"])
        result = await EquipmentResolver(conn).resolve_filter("H-Alpha", rig_context=ctx)
        assert result.status == "resolved"
        assert result.equipment_id == ids["ha7"]

    async def test_line_name_ambiguous(self, equipment):
        conn, ids = equipment
        ctx = RigContext(rig_id=ids["rig_ambig"])
        result = await EquipmentResolver(conn).resolve_filter("Ha", rig_context=ctx)
        assert result.status == "ambiguous"
        assert result.equipment_id is None

    async def test_line_name_without_rig_context_unresolved(self, equipment):
        conn, _ = equipment
        before = await _observation_count(conn)
        result = await EquipmentResolver(conn).resolve_filter("Ha")
        assert result.status == "unresolved"
        assert await _observation_count(conn) == before + 1

    async def test_line_name_rig_without_matching_slot_unresolved(self, equipment):
        conn, ids = equipment
        ctx = RigContext(rig_id=ids["rig_empty"])
        result = await EquipmentResolver(conn).resolve_filter("Ha", rig_context=ctx)
        assert result.status == "unresolved"

    @pytest.mark.parametrize("blank", ["", "   ", None])
    async def test_blank_filter_is_unresolved_without_observation(self, equipment, blank):
        conn, ids = equipment
        before = await _observation_count(conn)
        result = await EquipmentResolver(conn).resolve_filter(
            blank, rig_context=RigContext(rig_id=ids["rig_unique"])
        )
        assert result.status == "unresolved"
        assert result.normalized_alias == ""
        assert await _observation_count(conn) == before

    async def test_missing_rig_filter_slot_table_falls_through(self, equipment):
        conn, ids = equipment
        await conn.execute("DROP TABLE rig_filter_slot")
        ctx = RigContext(rig_id=ids["rig_unique"])
        result = await EquipmentResolver(conn).resolve_filter("Ha", rig_context=ctx)
        assert result.status == "unresolved"  # OperationalError caught → unresolved

    async def test_non_missing_table_operational_error_propagates(self, equipment):
        # A locked/disk-full error must NOT be silently downgraded to "not in rig".
        conn, ids = equipment
        resolver = EquipmentResolver(conn)
        resolver.conn = AsyncMock()
        resolver.conn.execute.side_effect = aiosqlite.OperationalError("database is locked")
        with pytest.raises(aiosqlite.OperationalError, match="locked"):
            await resolver._resolve_filter_by_line_name(
                "Ha", "ha", RigContext(rig_id=ids["rig_unique"])
            )


# ── Promotion (§9) ───────────────────────────────────────────────────────────


class TestPromotion:
    async def test_confirm_creates_alias_and_marks_resolved(self, equipment):
        conn, ids = equipment
        resolver = EquipmentResolver(conn)
        await resolver.resolve_camera("Brand New Cam")
        cur = await conn.execute(
            "SELECT id FROM unresolved_equipment_observation "
            "WHERE normalized_alias = 'brand new cam'"
        )
        obs_id = (await cur.fetchone())["id"]

        alias_id = await confirm_unresolved_observation(conn, obs_id, ids["cam_active"])
        assert alias_id is not None

        cur = await conn.execute(
            "SELECT camera_id, confirmed, source FROM camera_alias WHERE alias = 'brand new cam'"
        )
        alias_row = await cur.fetchone()
        assert alias_row["camera_id"] == ids["cam_active"]
        assert alias_row["confirmed"] == 1
        assert alias_row["source"] == "user"

        cur = await conn.execute(
            "SELECT resolved_to_equipment_id, resolved_at "
            "FROM unresolved_equipment_observation WHERE id = ?",
            (obs_id,),
        )
        obs_row = await cur.fetchone()
        assert obs_row["resolved_to_equipment_id"] == ids["cam_active"]
        assert obs_row["resolved_at"] is not None

        # Subsequent resolve now hits the confirmed alias.
        again = await resolver.resolve_camera("Brand New Cam")
        assert again.status == "resolved"
        assert again.equipment_id == ids["cam_active"]

    async def test_confirm_unknown_observation_raises(self, equipment):
        conn, ids = equipment
        with pytest.raises(ValueError, match="no unresolved_equipment_observation"):
            await confirm_unresolved_observation(conn, 999999, ids["cam_active"])


# ── Stats + transaction ownership ────────────────────────────────────────────


class TestStatsAndTransaction:
    async def test_resolver_stats_accumulate(self, equipment):
        conn, ids = equipment
        resolver = EquipmentResolver(conn)
        stats = ResolverStats()
        await resolver.resolve_camera("ZWO ASI2600MM Pro", stats=stats)
        await resolver.resolve_camera("Old Camera", stats=stats)
        await resolver.resolve_camera("Unknown One", stats=stats)
        await resolver.resolve_camera("Unknown Two", stats=stats)
        await resolver.resolve_filter(
            "Ha", rig_context=RigContext(rig_id=ids["rig_ambig"]), stats=stats
        )
        assert stats.resolved == 1
        assert stats.resolved_retired == 1
        assert stats.unresolved == 2
        assert stats.ambiguous == 1
        assert stats.newly_observed == 2

    async def test_resolver_never_commits(self, equipment):
        conn, _ = equipment
        # A resolve that writes an observation, then rollback: if the resolver had
        # committed, the row would survive the rollback.
        await EquipmentResolver(conn).resolve_camera("Uncommitted Cam")
        cur = await conn.execute(
            "SELECT COUNT(*) AS n FROM unresolved_equipment_observation "
            "WHERE normalized_alias = 'uncommitted cam'"
        )
        assert (await cur.fetchone())["n"] == 1
        await conn.rollback()
        cur = await conn.execute(
            "SELECT COUNT(*) AS n FROM unresolved_equipment_observation "
            "WHERE normalized_alias = 'uncommitted cam'"
        )
        assert (await cur.fetchone())["n"] == 0
