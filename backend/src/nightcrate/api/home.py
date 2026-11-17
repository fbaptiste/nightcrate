"""Cheap database summary for the Home page."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException

from nightcrate.api.gallery import load_project_records
from nightcrate.api.home_models import (
    HomeIntegrationLine,
    HomeSummary,
    LatestPicture,
    LocationSummary,
    RecentProject,
    RigSummary,
    StageCounts,
)
from nightcrate.api.project_crops import load_project_crops
from nightcrate.api.project_sessions import compute_integration
from nightcrate.db.session import get_db, workspace_key
from nightcrate.services.astronomy import constellation_for_coords
from nightcrate.services.gallery import GalleryQuery, build_gallery, valid_session_date
from nightcrate.services.home import (
    LocationRank,
    RigRank,
    rank_forecast_locations,
    rank_locations,
    rank_rigs,
    stage_of,
    summarise_year,
    window_start,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/home", tags=["Projects"])


def _today() -> date:
    return date.today()


def _local_date(value: str) -> date:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone().date()


def _target_label(targets) -> str | None:
    names = [target.name for target in targets]
    return ", ".join(names) if names else None


async def _thumbnail_facts(conn) -> dict[int, tuple[str, bool]]:
    cursor = await conn.execute(
        """
        SELECT p.id,
               COUNT(pi.id) AS image_count,
               MAX(CASE WHEN pi.is_main = 1 THEN pi.id END) AS main_image_id,
               (SELECT pt.id FROM project_thumbnail pt
                WHERE pt.project_id = p.id AND pt.size = 'small') AS crop_small_id,
               (SELECT pt.id FROM project_thumbnail pt
                WHERE pt.project_id = p.id AND pt.size = 'medium') AS crop_medium_id,
               (SELECT pt.id FROM project_thumbnail pt
                WHERE pt.project_id = p.id AND pt.size = 'large') AS crop_large_id
        FROM project p
        LEFT JOIN project_image pi ON pi.project_id = p.id
        GROUP BY p.id
        """
    )
    result = {}
    for row in await cursor.fetchall():
        version = (
            f"{row['main_image_id'] if row['main_image_id'] is not None else '-'}"
            f".s{row['crop_small_id'] if row['crop_small_id'] is not None else '-'}"
            f".m{row['crop_medium_id'] if row['crop_medium_id'] is not None else '-'}"
            f".l{row['crop_large_id'] if row['crop_large_id'] is not None else '-'}"
        )
        result[int(row["id"])] = (version, int(row["image_count"]) > 0)
    return result


async def _constellations(conn, project_ids: set[int]) -> dict[int, str]:
    if not project_ids:
        return {}
    placeholders = ",".join("?" * len(project_ids))
    cursor = await conn.execute(
        f"SELECT project_id, center_ra_deg, center_dec_deg FROM project_solve "  # nosec B608
        f"WHERE project_id IN ({placeholders})",
        tuple(project_ids),
    )
    return {
        int(row["project_id"]): constellation_for_coords(
            float(row["center_ra_deg"]), float(row["center_dec_deg"])
        )
        for row in await cursor.fetchall()
    }


@router.get("", response_model=HomeSummary)
async def get_home() -> HomeSummary:
    today = _today()
    since = window_start(today)
    try:
        async with get_db() as conn:
            project_cursor = await conn.execute(
                """
                SELECT p.id, p.name, p.status,
                       COALESCE(SUM(ps.exposure_seconds * ps.num_subs), 0) / 60.0 AS minutes
                FROM project p
                LEFT JOIN project_session ps ON ps.project_id = p.id
                WHERE p.active = 1
                GROUP BY p.id
                """
            )
            project_rows = await project_cursor.fetchall()
            stage_values = {name: 0 for name in StageCounts.model_fields}
            for row in project_rows:
                stage_values[stage_of(row["status"], float(row["minutes"]))] += 1

            records = await load_project_records(conn, with_object_facts=False)
            gallery = build_gallery(
                records,
                GalleryQuery(include_retired=False),
                target_search_hits=None,
                image_search_hits=None,
            )
            items = {item.project_id: item for item in gallery.items}
            recent_records = sorted(
                (record for record in records if not record.retired and record.dates),
                key=lambda record: (
                    -record.dates[-1].toordinal(),
                    record.name.casefold(),
                    record.id,
                ),
            )[:3]

            latest_cursor = await conn.execute(
                """
                SELECT pi.id, pi.project_id, pi.created_at
                FROM project_image pi
                JOIN project p ON p.id = pi.project_id
                WHERE p.active = 1
                ORDER BY pi.created_at DESC, pi.id DESC
                LIMIT 1
                """
            )
            latest_row = await latest_cursor.fetchone()
            detail_ids = {record.id for record in recent_records}
            if latest_row is not None:
                detail_ids.add(int(latest_row["project_id"]))
            constellations = await _constellations(conn, detail_ids)
            thumbnails = await _thumbnail_facts(conn)
            crops = await load_project_crops(conn, sorted(detail_ids))

            recent = []
            for record in recent_records:
                integration = await compute_integration(conn, record.id)
                item = items[record.id]
                thumbnail_version, has_image = thumbnails[record.id]
                recent.append(
                    RecentProject(
                        project_id=record.id,
                        name=record.name,
                        status=record.status,
                        stage=stage_of(record.status, integration.total_actual_minutes),
                        target_label=_target_label(item.targets),
                        constellation=constellations.get(record.id),
                        thumbnail_version=thumbnail_version,
                        has_image=has_image,
                        crops=crops.get(record.id, {}),
                        total_minutes=integration.total_actual_minutes,
                        lines=[
                            HomeIntegrationLine(
                                label=line.label,
                                minutes=line.actual_minutes,
                                not_recorded=line.not_recorded,
                            )
                            for line in integration.lines
                        ],
                        last_date=date.fromisoformat(integration.last_session_date or ""),
                        nights=integration.night_count,
                    )
                )

            latest_picture = None
            if latest_row is not None:
                project_id = int(latest_row["project_id"])
                item = items[project_id]
                latest_picture = LatestPicture(
                    project_id=project_id,
                    project_name=item.name,
                    image_id=int(latest_row["id"]),
                    added=_local_date(latest_row["created_at"]),
                    status=item.status,
                    target_label=_target_label(item.targets),
                    constellation=constellations.get(project_id),
                    crops=crops.get(project_id, {}),
                )

            session_cursor = await conn.execute(
                """
                SELECT ps.project_id, p.name, ps.rig_id, p.location_id,
                       ps.session_date, ps.exposure_seconds * ps.num_subs / 60.0 AS minutes
                FROM project_session ps
                JOIN project p ON p.id = ps.project_id
                WHERE p.active = 1
                """
            )
            session_rows = await session_cursor.fetchall()
            year_sessions = []
            rig_usage: dict[int, list[tuple[date, float]]] = defaultdict(list)
            location_usage: dict[int, list[tuple[date, float]]] = defaultdict(list)
            for row in session_rows:
                session_date = valid_session_date(row["session_date"])
                if session_date is None:
                    continue
                minutes = float(row["minutes"])
                year_sessions.append((int(row["project_id"]), row["name"], session_date, minutes))
                if row["rig_id"] is not None:
                    rig_usage[int(row["rig_id"])].append((session_date, minutes))
                if row["location_id"] is not None:
                    location_usage[int(row["location_id"])].append((session_date, minutes))

            picture_cursor = await conn.execute(
                """
                SELECT pi.created_at
                FROM project_image pi
                JOIN project p ON p.id = pi.project_id
                WHERE p.active = 1
                """
            )
            picture_dates = [
                (_local_date(row["created_at"]),) for row in await picture_cursor.fetchall()
            ]
            year = summarise_year(year_sessions, picture_dates, today)

            rig_active_cursor = await conn.execute(
                """
                SELECT rig_id, COUNT(DISTINCT project_id) AS projects
                FROM (
                    SELECT pr.rig_id, p.id AS project_id
                    FROM project_rig pr JOIN project p ON p.id = pr.project_id
                    WHERE p.active = 1 AND p.status = 'active'
                    UNION
                    SELECT ps.rig_id, p.id AS project_id
                    FROM project_session ps JOIN project p ON p.id = ps.project_id
                    WHERE ps.rig_id IS NOT NULL AND p.active = 1 AND p.status = 'active'
                )
                GROUP BY rig_id
                """
            )
            rig_active = {
                int(row["rig_id"]): int(row["projects"])
                for row in await rig_active_cursor.fetchall()
            }
            rig_cursor = await conn.execute(
                "SELECT id, name, sort_order FROM rig WHERE active = 1 AND is_mine = 1"
            )
            rig_values = []
            for row in await rig_cursor.fetchall():
                rig_id = int(row["id"])
                usage = rig_usage.get(rig_id, [])
                in_window = [(day, value) for day, value in usage if since <= day <= today]
                rig_values.append(
                    RigRank(
                        rig_id=rig_id,
                        name=row["name"],
                        sort_order=int(row["sort_order"]),
                        minutes=sum(value for _, value in in_window),
                        nights=len({day for day, _ in in_window}),
                        last_used=max((day for day, _ in usage), default=None),
                        active_projects=rig_active.get(rig_id, 0),
                    )
                )

            location_cursor = await conn.execute(
                "SELECT id, name, is_default FROM location WHERE active = 1"
            )
            location_rows = await location_cursor.fetchall()
            active_location_cursor = await conn.execute(
                """
                SELECT location_id, COUNT(DISTINCT id) AS projects
                FROM project
                WHERE active = 1 AND status = 'active' AND location_id IS NOT NULL
                GROUP BY location_id
                """
            )
            active_locations = {
                int(row["location_id"]): int(row["projects"])
                for row in await active_location_cursor.fetchall()
            }
            location_values = []
            for row in location_rows:
                location_id = int(row["id"])
                usage = location_usage.get(location_id, [])
                in_window = [(day, value) for day, value in usage if since <= day <= today]
                location_values.append(
                    LocationRank(
                        location_id=location_id,
                        name=row["name"],
                        is_default=bool(row["is_default"]),
                        minutes=sum(value for _, value in in_window),
                        nights=len({day for day, _ in in_window}),
                        last_used=max((day for day, _ in usage), default=None),
                        active_projects=active_locations.get(location_id, 0),
                    )
                )

        return HomeSummary(
            today=today,
            stages=StageCounts(**stage_values),
            total_projects=len(project_rows),
            recent=recent,
            latest_picture=latest_picture,
            year=asdict(year),
            rigs=[RigSummary(**value.__dict__) for value in rank_rigs(rig_values)],
            locations=[
                LocationSummary(**value.__dict__) for value in rank_locations(location_values)
            ],
            forecast_locations=[
                asdict(value)
                for value in rank_forecast_locations(
                    [
                        (int(row["id"]), row["name"], bool(row["is_default"]))
                        for row in location_rows
                    ],
                    active_locations,
                )
            ],
            workspace_key=workspace_key(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[home] failed to build summary")
        raise HTTPException(status_code=500, detail="Failed to build Home summary") from exc
