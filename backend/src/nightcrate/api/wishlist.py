"""Target Wishlist & Planning API (v0.30.0).

Routes for managing the user's target wishlist:

    GET    /api/planner/wishlist/favorites          — favorite DSO ids (lightweight)
    GET    /api/planner/wishlist/favorites/full      — full list with plans
    POST   /api/planner/wishlist/favorites           — add favorite
    DELETE  /api/planner/wishlist/favorites/{dso_id}  — remove favorite
    PUT    /api/planner/wishlist/favorites/reorder   — reorder favorites

    GET    /api/planner/wishlist/plans               — list plans (optionally filtered)
    POST   /api/planner/wishlist/plans               — create plan
    PUT    /api/planner/wishlist/plans/{plan_id}      — update plan
    DELETE  /api/planner/wishlist/plans/{plan_id}      — delete plan

    GET    /api/planner/wishlist/calendar            — calendar data for Gantt view
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api._common import integrity_guard
from nightcrate.api.wishlist_models import (
    AddFavoriteRequest,
    CalendarResponse,
    CalendarTargetRow,
    CreatePlanRequest,
    CreateSectionRequest,
    DateRange,
    DateRangeOut,
    FavoriteDsoSummary,
    FavoriteFullItem,
    FavoriteIdsResponse,
    FavoritesFullResponse,
    MoveFavoriteRequest,
    PlanListResponse,
    PlanResponse,
    PlanSummary,
    RenameSectionRequest,
    ReorderFavoritesRequest,
    ReorderSectionsRequest,
    SectionResponse,
    UpdatePlanRequest,
)
from nightcrate.api.wishlist_models import (
    MoonPhaseMonth as MoonPhaseMonthOut,
)
from nightcrate.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/planner/wishlist", tags=["wishlist"])


# ── Date range helpers ───────────────────────────────────────────────────────


def _validate_date_ranges(ranges: list[DateRange]) -> None:
    for r in ranges:
        if r.start_date > r.end_date:
            raise HTTPException(
                status_code=422,
                detail=f"Start date {r.start_date} is after end date {r.end_date}",
            )
    sorted_ranges = sorted(ranges, key=lambda r: r.start_date)
    for i in range(1, len(sorted_ranges)):
        if sorted_ranges[i].start_date <= sorted_ranges[i - 1].end_date:
            prev_end = sorted_ranges[i - 1].end_date
            cur_start = sorted_ranges[i].start_date
            raise HTTPException(
                status_code=422,
                detail=f"Date ranges overlap: {prev_end} and {cur_start}",
            )


async def _save_date_ranges(conn, plan_id: int, ranges: list[DateRange]) -> None:
    await conn.execute("DELETE FROM target_plan_date_range WHERE plan_id = ?", (plan_id,))
    for r in ranges:
        await conn.execute(
            "INSERT INTO target_plan_date_range (plan_id, start_date, end_date) VALUES (?, ?, ?)",
            (plan_id, r.start_date, r.end_date),
        )


async def _load_date_ranges(conn, plan_ids: list[int]) -> dict[int, list[DateRangeOut]]:
    if not plan_ids:
        return {}
    placeholders = ",".join("?" for _ in plan_ids)
    cursor = await conn.execute(
        f"SELECT id, plan_id, start_date, end_date FROM target_plan_date_range "  # nosec B608
        f"WHERE plan_id IN ({placeholders}) ORDER BY start_date",
        plan_ids,
    )
    rows = await cursor.fetchall()
    result: dict[int, list[DateRangeOut]] = {}
    for r in rows:
        pid = int(r["plan_id"])
        result.setdefault(pid, []).append(
            DateRangeOut(id=int(r["id"]), start_date=r["start_date"], end_date=r["end_date"])
        )
    return result


# ── Sections ─────────────────────────────────────────────────────────────────


async def _load_sections(conn) -> list[SectionResponse]:
    cursor = await conn.execute(
        "SELECT id, name, sort_order FROM wishlist_section ORDER BY sort_order"
    )
    return [
        SectionResponse(id=int(r["id"]), name=r["name"], sort_order=int(r["sort_order"]))
        for r in await cursor.fetchall()
    ]


@router.get("/sections")
async def list_sections() -> list[SectionResponse]:
    async with get_db() as conn:
        return await _load_sections(conn)


@router.post("/sections", status_code=201)
async def create_section(body: CreateSectionRequest) -> SectionResponse:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM wishlist_section"
        )
        next_order = int((await cursor.fetchone())["next_order"])
        cursor = await conn.execute(
            "INSERT INTO wishlist_section (name, sort_order) VALUES (?, ?)",
            (body.name, next_order),
        )
        section_id = cursor.lastrowid
        await conn.commit()
        return SectionResponse(id=section_id, name=body.name, sort_order=next_order)


@router.put("/sections/{section_id}")
async def rename_section(section_id: int, body: RenameSectionRequest) -> SectionResponse:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id, sort_order FROM wishlist_section WHERE id = ?",
            (section_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Section not found")
        await conn.execute(
            "UPDATE wishlist_section SET name = ? WHERE id = ?",
            (body.name, section_id),
        )
        await conn.commit()
        return SectionResponse(id=section_id, name=body.name, sort_order=int(row["sort_order"]))


@router.delete("/sections/{section_id}", status_code=204)
async def delete_section(section_id: int) -> None:
    async with get_db() as conn:
        await conn.execute("DELETE FROM wishlist_section WHERE id = ?", (section_id,))
        await conn.commit()


@router.put("/sections/reorder")
async def reorder_sections(
    body: ReorderSectionsRequest,
) -> list[SectionResponse]:
    async with get_db() as conn:
        for idx, sid in enumerate(body.section_ids):
            await conn.execute(
                "UPDATE wishlist_section SET sort_order = ? WHERE id = ?",
                (idx, sid),
            )
        await conn.commit()
        return await _load_sections(conn)


# ── Favorites ────────────────────────────────────────────────────────────────


@router.get("/favorites")
async def list_favorite_ids() -> FavoriteIdsResponse:
    async with get_db() as conn:
        cursor = await conn.execute("SELECT dso_id FROM favorite_target ORDER BY sort_order")
        rows = await cursor.fetchall()
        return FavoriteIdsResponse(dso_ids=[int(r["dso_id"]) for r in rows])


@router.get("/favorites/full")
async def list_favorites_full() -> FavoritesFullResponse:
    async with get_db() as conn:
        sections = await _load_sections(conn)

        cursor = await conn.execute(
            """
            SELECT ft.dso_id, ft.sort_order, ft.section_id, ft.created_at,
                   d.primary_designation, d.common_name, d.obj_type,
                   d.constellation, d.ra_deg, d.dec_deg, d.mag_v,
                   d.maj_axis_arcmin
            FROM favorite_target ft
            JOIN dso d ON d.id = ft.dso_id
            ORDER BY ft.sort_order
            """
        )
        fav_rows = await cursor.fetchall()

        cursor = await conn.execute(
            """
            SELECT tp.id, tp.dso_id, tp.location_id, tp.horizon_id,
                   tp.rig_id, tp.moon_sep_deg, tp.notes,
                   tp.created_at, tp.updated_at,
                   l.name AS location_name,
                   lh.name AS horizon_name,
                   r.name AS rig_name
            FROM target_plan tp
            JOIN location l ON l.id = tp.location_id
            JOIN location_horizon lh ON lh.id = tp.horizon_id
            JOIN rig r ON r.id = tp.rig_id
            ORDER BY tp.created_at
            """
        )
        plan_rows = await cursor.fetchall()

        all_plan_ids = [int(r["id"]) for r in plan_rows]
        ranges_by_plan = await _load_date_ranges(conn, all_plan_ids)

    plans_by_dso: dict[int, list[PlanSummary]] = {}
    for r in plan_rows:
        dso_id = int(r["dso_id"])
        plan_id = int(r["id"])
        plans_by_dso.setdefault(dso_id, []).append(
            PlanSummary(
                id=plan_id,
                location_id=int(r["location_id"]),
                location_name=r["location_name"],
                horizon_id=int(r["horizon_id"]),
                horizon_name=r["horizon_name"],
                rig_id=int(r["rig_id"]),
                rig_name=r["rig_name"],
                moon_sep_deg=int(r["moon_sep_deg"]),
                date_ranges=ranges_by_plan.get(plan_id, []),
                notes=r["notes"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
        )

    items = []
    for r in fav_rows:
        dso_id = int(r["dso_id"])
        plans = plans_by_dso.get(dso_id, [])
        items.append(
            FavoriteFullItem(
                dso=FavoriteDsoSummary(
                    dso_id=dso_id,
                    primary_designation=r["primary_designation"],
                    common_name=r["common_name"],
                    obj_type=r["obj_type"],
                    constellation=r["constellation"],
                    ra_deg=r["ra_deg"],
                    dec_deg=r["dec_deg"],
                    mag_v=r["mag_v"],
                    maj_axis_arcmin=r["maj_axis_arcmin"],
                ),
                sort_order=int(r["sort_order"]),
                section_id=int(r["section_id"]) if r["section_id"] is not None else None,
                plan_count=len(plans),
                plans=plans,
                created_at=r["created_at"],
            )
        )

    return FavoritesFullResponse(items=items, sections=sections, total=len(items))


@router.post("/favorites", status_code=200)
async def add_favorite(body: AddFavoriteRequest) -> FavoriteIdsResponse:
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id FROM dso WHERE id = ? AND active = 1",
            (body.dso_id,),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"DSO {body.dso_id} not found")

        cursor = await conn.execute(
            "SELECT dso_id FROM favorite_target WHERE dso_id = ?",
            (body.dso_id,),
        )
        if await cursor.fetchone() is not None:
            return await list_favorite_ids()

        cursor = await conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM favorite_target"
        )
        next_order = int((await cursor.fetchone())["next_order"])

        await conn.execute(
            "INSERT INTO favorite_target (dso_id, sort_order) VALUES (?, ?)",
            (body.dso_id, next_order),
        )
        await conn.commit()

    return await list_favorite_ids()


@router.delete("/favorites/{dso_id}", status_code=204)
async def remove_favorite(dso_id: int) -> None:
    async with get_db() as conn:
        await conn.execute("DELETE FROM favorite_target WHERE dso_id = ?", (dso_id,))
        await conn.commit()


@router.put("/favorites/reorder")
async def reorder_favorites(body: ReorderFavoritesRequest) -> FavoriteIdsResponse:
    async with get_db() as conn:
        for item in body.items:
            await conn.execute(
                "UPDATE favorite_target SET sort_order = ?, section_id = ? WHERE dso_id = ?",
                (item.sort_order, item.section_id, item.dso_id),
            )
        await conn.commit()

    return await list_favorite_ids()


@router.put("/favorites/{dso_id}/move")
async def move_favorite(dso_id: int, body: MoveFavoriteRequest) -> None:
    async with get_db() as conn:
        await conn.execute(
            "UPDATE favorite_target SET section_id = ?, sort_order = ? WHERE dso_id = ?",
            (body.section_id, body.sort_order, dso_id),
        )
        await conn.commit()


# ── Plans ────────────────────────────────────────────────────────────────────


async def _resolve_plan_response(conn, plan_row, ranges: list[DateRangeOut]) -> PlanResponse:
    loc_cursor = await conn.execute(
        "SELECT name FROM location WHERE id = ?", (plan_row["location_id"],)
    )
    loc_row = await loc_cursor.fetchone()

    hz_cursor = await conn.execute(
        "SELECT name FROM location_horizon WHERE id = ?", (plan_row["horizon_id"],)
    )
    hz_row = await hz_cursor.fetchone()

    rig_cursor = await conn.execute("SELECT name FROM rig WHERE id = ?", (plan_row["rig_id"],))
    rig_row = await rig_cursor.fetchone()

    dso_cursor = await conn.execute(
        "SELECT primary_designation, common_name FROM dso WHERE id = ?",
        (plan_row["dso_id"],),
    )
    dso_row = await dso_cursor.fetchone()

    return PlanResponse(
        id=int(plan_row["id"]),
        dso_id=int(plan_row["dso_id"]),
        primary_designation=dso_row["primary_designation"] if dso_row else "",
        common_name=dso_row["common_name"] if dso_row else None,
        location_id=int(plan_row["location_id"]),
        location_name=loc_row["name"] if loc_row else "(deleted)",
        horizon_id=int(plan_row["horizon_id"]),
        horizon_name=hz_row["name"] if hz_row else "(deleted)",
        rig_id=int(plan_row["rig_id"]),
        rig_name=rig_row["name"] if rig_row else "(deleted)",
        moon_sep_deg=int(plan_row["moon_sep_deg"]),
        date_ranges=ranges,
        notes=plan_row["notes"],
        created_at=plan_row["created_at"],
        updated_at=plan_row["updated_at"],
    )


@router.post("/plans", status_code=201)
async def create_plan(body: CreatePlanRequest) -> PlanResponse:
    if body.date_ranges:
        _validate_date_ranges(body.date_ranges)

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT id FROM dso WHERE id = ? AND active = 1",
            (body.dso_id,),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"DSO {body.dso_id} not found")

        cursor = await conn.execute(
            "SELECT id FROM location WHERE id = ? AND active = 1",
            (body.location_id,),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Location {body.location_id} not found")

        cursor = await conn.execute(
            "SELECT id FROM location_horizon WHERE id = ? AND location_id = ?",
            (body.horizon_id, body.location_id),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail=f"Horizon {body.horizon_id} not found for location {body.location_id}",
            )

        cursor = await conn.execute(
            "SELECT id FROM rig WHERE id = ? AND active = 1",
            (body.rig_id,),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Rig {body.rig_id} not found")

        cursor = await conn.execute(
            "SELECT dso_id FROM favorite_target WHERE dso_id = ?",
            (body.dso_id,),
        )
        if await cursor.fetchone() is None:
            next_cursor = await conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM favorite_target"
            )
            next_order = int((await next_cursor.fetchone())["next_order"])
            await conn.execute(
                "INSERT INTO favorite_target (dso_id, sort_order) VALUES (?, ?)",
                (body.dso_id, next_order),
            )

        with integrity_guard(
            conflict_detail="A plan with this DSO, location, horizon, and rig already exists",
        ):
            cursor = await conn.execute(
                """
                INSERT INTO target_plan
                    (dso_id, location_id, horizon_id, rig_id, moon_sep_deg, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    body.dso_id,
                    body.location_id,
                    body.horizon_id,
                    body.rig_id,
                    body.moon_sep_deg,
                    body.notes,
                ),
            )
            plan_id = cursor.lastrowid

            if body.date_ranges:
                await _save_date_ranges(conn, plan_id, body.date_ranges)

            await conn.commit()

        cursor = await conn.execute("SELECT * FROM target_plan WHERE id = ?", (plan_id,))
        row = await cursor.fetchone()
        ranges_map = await _load_date_ranges(conn, [plan_id])
        return await _resolve_plan_response(conn, row, ranges_map.get(plan_id, []))


@router.put("/plans/{plan_id}")
async def update_plan(plan_id: int, body: UpdatePlanRequest) -> PlanResponse:
    if body.date_ranges is not None and body.date_ranges:
        _validate_date_ranges(body.date_ranges)

    async with get_db() as conn:
        cursor = await conn.execute("SELECT * FROM target_plan WHERE id = ?", (plan_id,))
        existing = await cursor.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        location_id = body.location_id if body.location_id is not None else existing["location_id"]
        horizon_id = body.horizon_id if body.horizon_id is not None else existing["horizon_id"]
        rig_id = body.rig_id if body.rig_id is not None else existing["rig_id"]

        if body.location_id is not None:
            cursor = await conn.execute(
                "SELECT id FROM location WHERE id = ? AND active = 1",
                (body.location_id,),
            )
            if await cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404, detail=f"Location {body.location_id} not found"
                )

        if body.horizon_id is not None or body.location_id is not None:
            cursor = await conn.execute(
                "SELECT id FROM location_horizon WHERE id = ? AND location_id = ?",
                (horizon_id, location_id),
            )
            if await cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Horizon {horizon_id} not found for location {location_id}",
                )

        if body.rig_id is not None:
            cursor = await conn.execute(
                "SELECT id FROM rig WHERE id = ? AND active = 1",
                (body.rig_id,),
            )
            if await cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"Rig {body.rig_id} not found")

        moon_sep = body.moon_sep_deg if body.moon_sep_deg is not None else existing["moon_sep_deg"]

        notes = existing["notes"]
        if body.clear_notes:
            notes = None
        elif body.notes is not None:
            notes = body.notes

        with integrity_guard(
            conflict_detail="A plan with this DSO, location, horizon, and rig already exists",
        ):
            await conn.execute(
                """
                UPDATE target_plan
                SET location_id = ?, horizon_id = ?, rig_id = ?,
                    moon_sep_deg = ?, notes = ?
                WHERE id = ?
                """,
                (location_id, horizon_id, rig_id, moon_sep, notes, plan_id),
            )

            if body.date_ranges is not None:
                await _save_date_ranges(conn, plan_id, body.date_ranges)

            await conn.commit()

        cursor = await conn.execute("SELECT * FROM target_plan WHERE id = ?", (plan_id,))
        row = await cursor.fetchone()
        ranges_map = await _load_date_ranges(conn, [plan_id])
        return await _resolve_plan_response(conn, row, ranges_map.get(plan_id, []))


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_plan(plan_id: int) -> None:
    async with get_db() as conn:
        await conn.execute("DELETE FROM target_plan WHERE id = ?", (plan_id,))
        await conn.commit()


@router.get("/plans")
async def list_plans(
    location_id: int | None = Query(None),
    rig_id: int | None = Query(None),
) -> PlanListResponse:
    async with get_db() as conn:
        conditions = []
        params: list[int] = []
        if location_id is not None:
            conditions.append("tp.location_id = ?")
            params.append(location_id)
        if rig_id is not None:
            conditions.append("tp.rig_id = ?")
            params.append(rig_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        cursor = await conn.execute(
            f"""
            SELECT tp.*, d.primary_designation, d.common_name,
                   l.name AS location_name,
                   lh.name AS horizon_name,
                   r.name AS rig_name
            FROM target_plan tp
            JOIN dso d ON d.id = tp.dso_id
            JOIN location l ON l.id = tp.location_id
            JOIN location_horizon lh ON lh.id = tp.horizon_id
            JOIN rig r ON r.id = tp.rig_id
            {where}
            ORDER BY tp.created_at
            """,  # nosec B608 — where clause from internal logic, not user input
            params,
        )
        rows = await cursor.fetchall()

        all_plan_ids = [int(r["id"]) for r in rows]
        ranges_by_plan = await _load_date_ranges(conn, all_plan_ids)

        items = [
            PlanResponse(
                id=int(r["id"]),
                dso_id=int(r["dso_id"]),
                primary_designation=r["primary_designation"],
                common_name=r["common_name"],
                location_id=int(r["location_id"]),
                location_name=r["location_name"],
                horizon_id=int(r["horizon_id"]),
                horizon_name=r["horizon_name"],
                rig_id=int(r["rig_id"]),
                rig_name=r["rig_name"],
                moon_sep_deg=int(r["moon_sep_deg"]),
                date_ranges=ranges_by_plan.get(int(r["id"]), []),
                notes=r["notes"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    return PlanListResponse(items=items, total=len(items))


# ── Calendar ─────────────────────────────────────────────────────────────────


@router.get("/calendar")
async def get_calendar_data(
    location_id: int = Query(...),
    horizon_id: int = Query(...),
    rig_id: int = Query(...),
    start_month: str = Query(None),
    months: int = Query(13),
) -> CalendarResponse:
    from nightcrate.services.planner_calendar import (
        _compute_moon_phases,
        _generate_month_labels,
    )

    if start_month:
        try:
            sm = date.fromisoformat(f"{start_month}-01")
        except ValueError:
            raise HTTPException(status_code=422, detail="start_month must be YYYY-MM")
    else:
        sm = date(date.today().year, 1, 1)
        months = 12

    async with get_db() as conn:
        loc_cursor = await conn.execute(
            "SELECT name FROM location WHERE id = ? AND active = 1",
            (location_id,),
        )
        loc_row = await loc_cursor.fetchone()
        if loc_row is None:
            raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
        location_name = loc_row["name"]

        rig_cursor = await conn.execute(
            "SELECT name FROM rig WHERE id = ? AND active = 1",
            (rig_id,),
        )
        rig_row = await rig_cursor.fetchone()
        if rig_row is None:
            raise HTTPException(status_code=404, detail=f"Rig {rig_id} not found")
        rig_name = rig_row["name"]

        plan_cursor = await conn.execute(
            """
            SELECT tp.id AS plan_id, tp.dso_id, tp.notes,
                   d.primary_designation, d.common_name,
                   ft.section_id, ws.name AS section_name,
                   COALESCE(ws.sort_order, 999999) AS section_sort
            FROM target_plan tp
            JOIN dso d ON d.id = tp.dso_id
            JOIN favorite_target ft ON ft.dso_id = tp.dso_id
            LEFT JOIN wishlist_section ws ON ws.id = ft.section_id
            WHERE tp.location_id = ? AND tp.horizon_id = ? AND tp.rig_id = ?
            ORDER BY section_sort, ft.sort_order
            """,
            (location_id, horizon_id, rig_id),
        )
        plan_rows = await plan_cursor.fetchall()

        all_plan_ids = [int(r["plan_id"]) for r in plan_rows]
        ranges_by_plan = await _load_date_ranges(conn, all_plan_ids)
        sections = await _load_sections(conn)

    plans_with_ranges = [r for r in plan_rows if ranges_by_plan.get(int(r["plan_id"]))]

    empty = CalendarResponse(
        location_id=location_id,
        location_name=location_name,
        rig_id=rig_id,
        rig_name=rig_name,
        horizon_id=0,
        horizon_name="",
        months=[],
        targets=[],
        sections=[],
        moon_phases=[],
    )
    if not plans_with_ranges:
        return empty

    month_labels = _generate_month_labels(sm, months)
    moon_phases = await asyncio.to_thread(_compute_moon_phases, month_labels)

    targets_out = [
        CalendarTargetRow(
            dso_id=int(r["dso_id"]),
            primary_designation=r["primary_designation"],
            common_name=r["common_name"],
            plan_id=int(r["plan_id"]),
            date_ranges=ranges_by_plan.get(int(r["plan_id"]), []),
            notes=r["notes"],
            monthly_hours=[],
            section_id=int(r["section_id"]) if r["section_id"] else None,
            section_name=r["section_name"],
        )
        for r in plans_with_ranges
    ]

    return CalendarResponse(
        location_id=location_id,
        location_name=location_name,
        rig_id=rig_id,
        rig_name=rig_name,
        horizon_id=0,
        horizon_name="",
        months=month_labels,
        targets=targets_out,
        sections=sections,
        moon_phases=[
            MoonPhaseMonthOut(
                month=mp.month,
                new_moon_date=mp.new_moon_date,
                full_moon_date=mp.full_moon_date,
            )
            for mp in moon_phases
        ],
    )
