"""Unresolved-equipment review endpoints (v0.41.0).

The HTTP boundary over the ``unresolved_equipment_observation`` queue that the
resolver populates during ingest. A human maps each pending header string to an
equipment row ("confirm" — inserts a ``confirmed = 1`` alias via the resolver's
promotion helper) or dismisses it. The resolver itself never auto-confirms.

Dismissal deletes the observation; if the same header value is seen by a later
ingest it reappears with a fresh ``seen_count`` (a deliberate "not now" rather
than a permanent suppression).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nightcrate.api._common import get_or_404, integrity_guard, row_to_dict
from nightcrate.db.session import get_db
from nightcrate.services.equipment_resolver import (
    canonicalize_line_name,
    confirm_unresolved_observation,
)

logger = logging.getLogger("nightcrate.equipment_aliases")

router = APIRouter(prefix="/api/equipment/unresolved", tags=["Equipment Aliases"])

# equipment_kind doubles as its equipment table name. Closed vocabulary — the
# CHECK on unresolved_equipment_observation.equipment_kind (migration 0005) is
# the enforcement; this set only keeps a bad kind from reaching a table name.
_KIND_TABLES = frozenset({"camera", "telescope", "filter"})


class UnresolvedObservation(BaseModel):
    id: int
    equipment_kind: str  # camera | telescope | filter
    normalized_alias: str
    original_observation: str
    first_seen_at: str
    last_seen_at: str
    seen_count: int
    source: str
    resolved_to_equipment_id: int | None = None
    resolved_at: str | None = None


class UnresolvedObservationsPage(BaseModel):
    items: list[UnresolvedObservation]
    pending_total: int
    pending_by_kind: dict[str, int]


class ConfirmObservation(BaseModel):
    equipment_id: int


class ConfirmResult(BaseModel):
    alias_id: int
    observation: UnresolvedObservation


@router.get("", response_model=UnresolvedObservationsPage)
async def list_unresolved() -> UnresolvedObservationsPage:
    """Pending observations (most-seen first), plus per-kind pending counts."""
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM unresolved_equipment_observation "
            "WHERE resolved_at IS NULL ORDER BY seen_count DESC, last_seen_at DESC",
        )
        items = [UnresolvedObservation(**row_to_dict(r)) for r in await cursor.fetchall()]
        cursor = await conn.execute(
            "SELECT equipment_kind, COUNT(*) AS n FROM unresolved_equipment_observation "
            "WHERE resolved_at IS NULL GROUP BY equipment_kind",
        )
        by_kind = {r["equipment_kind"]: r["n"] for r in await cursor.fetchall()}
        return UnresolvedObservationsPage(
            items=items,
            pending_total=sum(by_kind.values()),
            pending_by_kind=by_kind,
        )


@router.post("/{observation_id}/confirm", response_model=ConfirmResult)
async def confirm_observation(observation_id: int, body: ConfirmObservation) -> ConfirmResult:
    """Map a pending observation to an equipment row (human-only promotion).

    Inserts a confirmed alias and marks the observation resolved. Frames already
    cataloged pick the new alias up on the next re-scan or resolution re-run.
    """
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        obs = await get_or_404(
            conn, "unresolved_equipment_observation", observation_id, "Observation"
        )
        if obs["resolved_at"] is not None:
            raise HTTPException(status_code=409, detail="Observation is already resolved")
        table = obs["equipment_kind"]
        if table not in _KIND_TABLES:  # pragma: no cover - CHECK makes this unreachable
            raise HTTPException(status_code=422, detail="Unknown equipment kind")
        # A confirmed alias is global, so mapping a canonical line name to one
        # physical filter would be wrong for anyone running two rigs — the only
        # correct resolution is rig-scoped via rig_filter_slot. v0.41.0 stopped
        # recording these, and migration 0042 purged the rows earlier versions
        # queued, but refuse explicitly so a stale client can't recreate one.
        if table == "filter" and canonicalize_line_name(obs["normalized_alias"]) is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'{obs['original_observation']}' is a filter bandpass, not a specific "
                    "filter. Mapping it would apply to every rig. Assign the rig to the "
                    "project instead — its filter slots resolve the bandpass per rig."
                ),
            )
        await get_or_404(conn, table, body.equipment_id, table.capitalize())

        with integrity_guard(conflict_detail="An alias with this value already exists"):
            alias_id = await confirm_unresolved_observation(
                conn, observation_id, body.equipment_id, source="user"
            )
            await conn.commit()

        refreshed = await get_or_404(
            conn, "unresolved_equipment_observation", observation_id, "Observation"
        )
        return ConfirmResult(alias_id=alias_id, observation=UnresolvedObservation(**refreshed))


@router.delete("/{observation_id}", status_code=204)
async def dismiss_observation(observation_id: int) -> None:
    """Drop a pending observation (it reappears if a later ingest sees it again)."""
    async with get_db() as conn:
        await get_or_404(conn, "unresolved_equipment_observation", observation_id, "Observation")
        await conn.execute(
            "DELETE FROM unresolved_equipment_observation WHERE id = ?", (observation_id,)
        )
        await conn.commit()
