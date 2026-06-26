"""FITS equipment resolver — map raw FITS header strings to equipment rows.

Takes values from FITS headers (``INSTRUME``, ``TELESCOP``, ``FILTER``) and
resolves them to rows in the equipment database (``camera``, ``telescope``,
``filter``) — or records them as *unresolved observations* for later human
mapping. The resolver is **deterministic**: exact match against a normalized
alias table after normalization (§4). No fuzzy matching, no Levenshtein, no ML.

See ``PLAN.md`` → "FITS Equipment Resolver Spec" (§1–§11) for the full design.

Architecture invariants:

- **Pure service.** Must not import from ``api/``.
- **Caller owns the transaction.** The resolver writes during normal operation
  (bumps ``last_seen_at``, upserts unresolved observations, inserts confirmed
  aliases on promotion) but never ``commit()`` or ``rollback()``s — so an ingest
  run can wrap many resolve calls in one transaction.
- **Never raises for unresolved.** Unresolved is a normal outcome; the resolver
  returns a structured result and lets the caller carry on with whatever *did*
  resolve.
- **Never auto-confirms.** Alias promotion (``confirmed = 1``) is a human-only
  action via :func:`confirm_unresolved_observation`.

Two-camera-same-model limitation (§7): two physically distinct ASI 2600MM Pro
bodies both emit ``INSTRUME = "ZWO ASI2600MM Pro"``. The ``UNIQUE(alias)``
constraint means that string maps to exactly one ``camera`` row, so the resolver
returns whichever camera the alias points at. Rig-level disambiguation (by
mount / telescope / filter-wheel / capturing host) is the ingest pipeline's job
(v0.41.0), not the alias resolver's.

Filter line-name scoping (§6): ``FILTER = "Ha"`` is a slot label, not a model
name. ``resolve_filter`` first tries an exact alias lookup, then — if a rig
context is supplied — scopes a canonicalized line name to the filters loaded in
that rig via ``rig_filter_slot``. Exactly one candidate resolves; more than one
is ``ambiguous``; none falls through to unresolved.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

import aiosqlite
from pydantic import BaseModel

logger = logging.getLogger("nightcrate.equipment_resolver")

_LOG_PREFIX = "[equipment-resolver]"

# Equipment kind → (alias table, FK column on that alias table, equipment table).
# Closed internal allow-list — these strings are never user-supplied, which is
# why the f-string SQL below is safe (see the `# nosec B608` annotations).
_KIND_CONFIG: dict[str, tuple[str, str, str]] = {
    "camera": ("camera_alias", "camera_id", "camera"),
    "telescope": ("telescope_alias", "telescope_id", "telescope"),
    "filter": ("filter_alias", "filter_id", "filter"),
}

_WHITESPACE_RE = re.compile(r"\s+")

EquipmentKind = Literal["camera", "telescope", "filter"]
ObservationSource = Literal["nina", "asiair", "user", "manual"]
ResolveStatus = Literal["resolved", "resolved_retired", "unresolved", "ambiguous"]


# ── Normalization (§4) ──────────────────────────────────────────────────────


def normalize_alias(value: str) -> str:
    """Return the canonical, comparison-ready form of a raw header value (§4).

    Deterministic pipeline, applied in order:

    1. Unicode NFKC normalization.
    2. Strip leading / trailing whitespace.
    3. Collapse internal whitespace runs to a single space.
    4. Remove zero-width and control characters (Unicode category ``C*``),
       keeping the regular spaces produced by step 3.
    5. Lowercase.

    Punctuation, hyphens, slashes and parentheses are **preserved** — ``"7nm Ha"``
    and ``"7 nm Ha"`` are intentionally different aliases. The result is what the
    resolver stores and matches against; the raw string is kept only for display
    in the unresolved-observation table.
    """
    s = unicodedata.normalize("NFKC", value)
    s = s.strip()
    s = _WHITESPACE_RE.sub(" ", s)
    s = "".join(ch for ch in s if ch == " " or not unicodedata.category(ch).startswith("C"))
    return s.lower()


# ── Line-name canonicalization (§6) ─────────────────────────────────────────

# Closed, code-level map (grows only by code change). Keys are the
# `normalize_alias`-normalized form of accepted header spellings; values are the
# canonical `line_name` vocabulary (a subset of the filter_passband.line_name
# CHECK constraint). A value not in this map is "not a line name" → the caller
# falls back to the regular alias lookup, so physical model names still resolve.
_LINE_NAME_MAP: dict[str, str] = {
    # Ha
    "ha": "Ha",
    "h-a": "Ha",
    "h alpha": "Ha",
    "h-alpha": "Ha",
    "halpha": "Ha",
    "hydrogen alpha": "Ha",
    "hydrogen-alpha": "Ha",
    # Hb
    "hb": "Hb",
    "h-b": "Hb",
    "h beta": "Hb",
    "h-beta": "Hb",
    "hbeta": "Hb",
    "hydrogen beta": "Hb",
    # Oiii
    "oiii": "Oiii",
    "o3": "Oiii",
    "o-iii": "Oiii",
    "o iii": "Oiii",
    "oxygen iii": "Oiii",
    "oxygen-iii": "Oiii",
    "oxygeniii": "Oiii",
    # Sii
    "sii": "Sii",
    "s2": "Sii",
    "s-ii": "Sii",
    "s ii": "Sii",
    "sulfur ii": "Sii",
    "sulphur ii": "Sii",
    "sulfur-ii": "Sii",
    # Lum
    "l": "Lum",
    "lum": "Lum",
    "luminance": "Lum",
    "clear": "Lum",
    # R / G / B
    "r": "R",
    "red": "R",
    "g": "G",
    "green": "G",
    "b": "B",
    "blue": "B",
    # UVIR
    "uvir": "UVIR",
    "uv/ir": "UVIR",
    "uv-ir": "UVIR",
    "uv ir cut": "UVIR",
}


def canonicalize_line_name(value: str) -> str | None:
    """Fold a FITS ``FILTER`` spelling onto the canonical ``line_name`` vocabulary.

    Returns ``None`` when *value* isn't a recognized line name — the caller then
    falls back to the regular alias lookup so a physical model name like
    ``"Optolong L-Pro"`` still resolves normally.
    """
    if not value:
        return None
    return _LINE_NAME_MAP.get(normalize_alias(value))


def _line_name_from_normalized(normalized: str) -> str | None:
    """Line-name lookup on an already-normalized value (avoids re-normalizing)."""
    return _LINE_NAME_MAP.get(normalized)


# ── Result + context shapes ─────────────────────────────────────────────────


class ResolveResult(BaseModel):
    """Outcome of a single resolve call.

    - ``resolved`` — matched an alias pointing at an active equipment row.
    - ``resolved_retired`` — matched an alias pointing at an ``active = 0`` row
      (still returned; the header is probably from a session before retirement).
    - ``unresolved`` — no match; a new/repeat observation was recorded.
    - ``ambiguous`` — a line name mapped to more than one filter in the rig.
    """

    status: ResolveStatus
    equipment_id: int | None = None
    equipment: dict | None = None
    normalized_alias: str
    newly_observed: bool = False
    message: str | None = None


class RigContext(BaseModel):
    """Identity of the rig that captured a frame — scopes filter line-name lookup.

    Resolved earlier in the same ingest run. ``None`` (no context) means line-name
    resolution cannot run, so ``resolve_filter`` does exact-alias-then-unresolved.
    """

    rig_id: int


@dataclass
class ResolverStats:
    """Optional per-run accumulator for ingest-summary reporting (§10)."""

    resolved: int = 0
    resolved_retired: int = 0
    unresolved: int = 0
    ambiguous: int = 0
    newly_observed: int = 0

    def record(self, result: ResolveResult) -> None:
        if result.status == "resolved":
            self.resolved += 1
        elif result.status == "resolved_retired":
            self.resolved_retired += 1
        elif result.status == "unresolved":
            self.unresolved += 1
        elif result.status == "ambiguous":
            self.ambiguous += 1
        if result.newly_observed:
            self.newly_observed += 1


# ── Resolver ────────────────────────────────────────────────────────────────


class EquipmentResolver:
    """Stateless resolver over an open connection. Safe to instantiate per run."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def resolve_camera(
        self,
        header_value: str | None,
        *,
        source: ObservationSource = "nina",
        stats: ResolverStats | None = None,
    ) -> ResolveResult:
        return await self._resolve("camera", header_value, source=source, stats=stats)

    async def resolve_telescope(
        self,
        header_value: str | None,
        *,
        source: ObservationSource = "nina",
        stats: ResolverStats | None = None,
    ) -> ResolveResult:
        return await self._resolve("telescope", header_value, source=source, stats=stats)

    async def resolve_filter(
        self,
        header_value: str | None,
        *,
        source: ObservationSource = "nina",
        rig_context: RigContext | None = None,
        stats: ResolverStats | None = None,
    ) -> ResolveResult:
        """Resolve a ``FILTER`` header: exact alias → rig-scoped line name → unresolved (§6)."""
        normalized = normalize_alias(header_value or "")
        if not normalized:
            return _finish(
                ResolveResult(
                    status="unresolved", normalized_alias="", message="blank header value"
                ),
                stats,
            )

        # 1. Exact alias lookup (handles physical model-name headers).
        hit = await self._lookup_alias("filter", normalized)
        if hit is not None:
            return _finish(hit, stats)

        # 2. Line-name canonicalization scoped to the capturing rig's filters.
        #    Reuse the already-normalized value rather than re-normalizing.
        line_name = _line_name_from_normalized(normalized)
        if line_name is not None and rig_context is not None:
            scoped = await self._resolve_filter_by_line_name(line_name, normalized, rig_context)
            if scoped is not None:
                return _finish(scoped, stats)

        # 3. Unresolved — record the observation.
        miss = await self._record_unresolved("filter", normalized, header_value or "", source)
        return _finish(miss, stats)

    # ── shared internals ────────────────────────────────────────────────────

    async def _resolve(
        self,
        kind: EquipmentKind,
        header_value: str | None,
        *,
        source: ObservationSource,
        stats: ResolverStats | None,
    ) -> ResolveResult:
        """Shared camera/telescope algorithm (§5): normalize → alias lookup → unresolved."""
        normalized = normalize_alias(header_value or "")
        if not normalized:
            return _finish(
                ResolveResult(
                    status="unresolved", normalized_alias="", message="blank header value"
                ),
                stats,
            )
        hit = await self._lookup_alias(kind, normalized)
        if hit is not None:
            return _finish(hit, stats)
        miss = await self._record_unresolved(kind, normalized, header_value or "", source)
        return _finish(miss, stats)

    async def _lookup_alias(self, kind: EquipmentKind, normalized: str) -> ResolveResult | None:
        """Look up *normalized* in the alias table; bump ``last_seen_at`` on a hit.

        Returns a ``resolved`` / ``resolved_retired`` result, or ``None`` on a miss.
        """
        alias_table, fk_col, eq_table = _KIND_CONFIG[kind]
        cursor = await self.conn.execute(
            f"SELECT al.id AS _alias_id, eq.* "  # nosec B608 - table names from internal allow-list, not user input
            f"FROM {alias_table} al JOIN {eq_table} eq ON eq.id = al.{fk_col} "
            f"WHERE al.alias = ?",
            (normalized,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        equipment = dict(row)
        alias_id = equipment.pop("_alias_id")
        await self.conn.execute(
            f"UPDATE {alias_table} SET last_seen_at = datetime('now') WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
            (alias_id,),
        )

        if equipment.get("active") == 0:
            logger.warning(
                "%s resolved '%s' to RETIRED %s id=%s",
                _LOG_PREFIX,
                normalized,
                eq_table,
                equipment["id"],
            )
            return ResolveResult(
                status="resolved_retired",
                equipment_id=equipment["id"],
                equipment=equipment,
                normalized_alias=normalized,
                message=f"{eq_table} is retired (active=0)",
            )

        logger.debug(
            "%s resolved %s '%s' -> id=%s", _LOG_PREFIX, eq_table, normalized, equipment["id"]
        )
        return ResolveResult(
            status="resolved",
            equipment_id=equipment["id"],
            equipment=equipment,
            normalized_alias=normalized,
        )

    async def _resolve_filter_by_line_name(
        self, line_name: str, normalized: str, rig_context: RigContext
    ) -> ResolveResult | None:
        """Scope *line_name* to the filters loaded in the rig via ``rig_filter_slot`` (§6).

        Exactly one active candidate → ``resolved``; more than one → ``ambiguous``;
        none → ``None`` (fall through to unresolved). ``rig_filter_slot`` exists since
        migration 0009, so its absence is not expected; if it is ever genuinely
        missing we warn and fall through (forward-compatible safety net). Any other
        operational error (locked DB, disk full, …) propagates rather than silently
        downgrading to "filter not in rig".
        """
        try:
            cursor = await self.conn.execute(
                "SELECT DISTINCT f.* "
                "FROM filter_passband fp "
                "JOIN filter f ON f.id = fp.filter_id "
                "JOIN rig_filter_slot rfs ON rfs.filter_id = f.id "
                "WHERE fp.line_name = ? AND fp.active = 1 AND f.active = 1 AND rfs.rig_id = ?",
                (line_name, rig_context.rig_id),
            )
            rows = await cursor.fetchall()
        except aiosqlite.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            logger.warning(
                "%s rig_filter_slot missing (%s); falling through to unresolved",
                _LOG_PREFIX,
                exc,
            )
            return None

        if not rows:
            return None
        if len(rows) > 1:
            logger.warning(
                "%s line name '%s' ambiguous in rig %d (%d candidate filters)",
                _LOG_PREFIX,
                line_name,
                rig_context.rig_id,
                len(rows),
            )
            return ResolveResult(
                status="ambiguous",
                normalized_alias=normalized,
                message=(
                    f"line name '{line_name}' matches {len(rows)} filters in rig "
                    f"{rig_context.rig_id}"
                ),
            )

        equipment = dict(rows[0])
        logger.debug(
            "%s resolved filter '%s' via line name '%s' scoped to rig %d -> id=%s",
            _LOG_PREFIX,
            normalized,
            line_name,
            rig_context.rig_id,
            equipment["id"],
        )
        return ResolveResult(
            status="resolved",
            equipment_id=equipment["id"],
            equipment=equipment,
            normalized_alias=normalized,
            message=f"resolved via line name '{line_name}' scoped to rig {rig_context.rig_id}",
        )

    async def _record_unresolved(
        self,
        kind: EquipmentKind,
        normalized: str,
        original: str,
        source: ObservationSource,
    ) -> ResolveResult:
        """Upsert into ``unresolved_equipment_observation`` and return ``unresolved``."""
        cursor = await self.conn.execute(
            "SELECT id, seen_count FROM unresolved_equipment_observation "
            "WHERE equipment_kind = ? AND normalized_alias = ?",
            (kind, normalized),
        )
        existing = await cursor.fetchone()
        if existing is None:
            await self.conn.execute(
                "INSERT INTO unresolved_equipment_observation "
                "(equipment_kind, normalized_alias, original_observation, source) "
                "VALUES (?, ?, ?, ?)",
                (kind, normalized, original, source),
            )
            logger.info(
                "%s new unresolved %s observation: '%s' (raw=%r, source=%s)",
                _LOG_PREFIX,
                kind,
                normalized,
                original,
                source,
            )
            newly = True
        else:
            await self.conn.execute(
                "UPDATE unresolved_equipment_observation "
                "SET seen_count = seen_count + 1, last_seen_at = datetime('now'), "
                "original_observation = ? WHERE id = ?",
                (original, existing["id"]),
            )
            logger.debug(
                "%s repeat unresolved %s observation: '%s' (seen_count -> %d)",
                _LOG_PREFIX,
                kind,
                normalized,
                existing["seen_count"] + 1,
            )
            newly = False

        return ResolveResult(
            status="unresolved",
            normalized_alias=normalized,
            newly_observed=newly,
            message=f"no confident match for {kind} '{normalized}'",
        )


def _finish(result: ResolveResult, stats: ResolverStats | None) -> ResolveResult:
    """Record the outcome in *stats* (if given) and return *result*."""
    if stats is not None:
        stats.record(result)
    return result


# ── Promotion (§9) ──────────────────────────────────────────────────────────


async def confirm_unresolved_observation(
    conn: aiosqlite.Connection,
    observation_id: int,
    equipment_id: int,
    *,
    source: Literal["user", "manual"] = "user",
) -> int:
    """Promote an unresolved observation to a **confirmed** alias (human action only).

    Inserts a ``confirmed = 1`` alias on the alias table for the observation's
    ``equipment_kind`` pointing at *equipment_id*, then marks the observation
    resolved (``resolved_to_equipment_id`` / ``resolved_at``) — retained for
    history, never deleted. The resolver never calls this itself; promotion is
    always a deliberate user action.

    The caller owns the transaction (no commit here). Returns the new alias id.
    """
    cursor = await conn.execute(
        "SELECT equipment_kind, normalized_alias "
        "FROM unresolved_equipment_observation WHERE id = ?",
        (observation_id,),
    )
    obs = await cursor.fetchone()
    if obs is None:
        raise ValueError(f"no unresolved_equipment_observation with id={observation_id}")

    kind = obs["equipment_kind"]
    alias_table, fk_col, _ = _KIND_CONFIG[kind]
    inserted = await conn.execute(
        f"INSERT INTO {alias_table} ({fk_col}, alias, source, confirmed) "  # nosec B608 - table/column names from internal allow-list, not user input
        f"VALUES (?, ?, ?, 1)",
        (equipment_id, obs["normalized_alias"], source),
    )
    await conn.execute(
        "UPDATE unresolved_equipment_observation "
        "SET resolved_to_equipment_id = ?, resolved_at = datetime('now') WHERE id = ?",
        (equipment_id, observation_id),
    )
    logger.info(
        "%s promoted observation id=%d (%s '%s') -> %s id=%d",
        _LOG_PREFIX,
        observation_id,
        kind,
        obs["normalized_alias"],
        kind,
        equipment_id,
    )
    return inserted.lastrowid
