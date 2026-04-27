"""Equipment factory — shared router builders for CRUD endpoints.

Two factories:

1. ``build_lookup_router`` — the 9 lookup tables (`manufacturer`,
   `optical_design`, `mount_type`, `connection_interface`, `connector_size`,
   `filter_size`, `form_factor`, `focuser_type`, `filter_type`) share an
   identical 5-endpoint CRUD pattern: list, get, create, update, soft-delete.

2. ``build_equipment_router`` — the 8 mid-complexity equipment tables
   (`camera`, `mount`, `focuser`, `filter_wheel`, `computer`, `oag`,
   `guide_scope`, `software`) share a 6-endpoint pattern: the lookup five
   plus a `POST /{id}/mine` toggle. Four of them (`camera`, `mount`,
   `focuser`, `filter_wheel`) additionally have an M2M interface-junction
   table rebuilt on create/update. ``software`` has a CHECK constraint on
   `category` that needs a 422 response.

Insertable columns for both factories are introspected from the Pydantic
Create model — there is no hand-written column list per table. The
equipment factory delegates the nested response shape (manufacturer,
interfaces, per-type lookups) to a caller-supplied ``response_builder``
since those nested joins differ enough per type that a generic is worse
than explicit code.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from nightcrate.api._common import bool_fields, get_or_404, integrity_guard, row_to_dict
from nightcrate.api.equipment_models import MineToggle
from nightcrate.db.session import get_db


def build_lookup_router(
    router: APIRouter,
    *,
    table: str,
    url_slug: str,
    label: str,
    create_model: type[BaseModel],
    update_model: type[BaseModel],
    response_model: type[BaseModel],
    order_by: str = "name",
    conflict_field: str = "name",
) -> None:
    """Register list / get / create / update / soft-delete endpoints for a lookup table.

    Args:
        router: The router to attach the five endpoints to.
        table: SQL table name (e.g. ``"optical_design"``).
        url_slug: URL fragment (e.g. ``"optical-design"``).
        label: Human-readable label used in 404 / 409 messages (e.g. ``"Optical design"``).
        create_model: Pydantic model for POST body. Field names must match table column names.
        update_model: Pydantic model for PUT body. All fields optional.
        response_model: Pydantic model for responses.
        order_by: SQL ORDER BY clause for the list endpoint. Default ``"name"``.
        conflict_field: Body attribute echoed in the 409 CREATE message (default ``"name"``).
    """
    create_columns = tuple(create_model.model_fields.keys())
    prefix = f"/{url_slug}"
    detail_prefix = f"/{url_slug}/{{item_id}}"

    @router.get(prefix, response_model=list[response_model], name=f"list_{table}")
    async def list_items(
        include_retired: bool = Query(False, description="Include retired items"),
    ) -> list[dict]:
        async with get_db() as conn:
            where = "" if include_retired else "WHERE active = 1"
            rows = await conn.execute(
                f"SELECT * FROM {table} {where} ORDER BY {order_by}"  # nosec B608 - table name from internal allow-list, not user input
            )
            return [bool_fields(row_to_dict(r), "active") for r in await rows.fetchall()]

    @router.get(detail_prefix, response_model=response_model, name=f"get_{table}")
    async def get_item(item_id: int) -> dict:
        async with get_db() as conn:
            return bool_fields(await get_or_404(conn, table, item_id, label), "active")

    @router.post(prefix, response_model=response_model, status_code=201, name=f"create_{table}")
    async def create_item(body: create_model) -> dict:  # type: ignore[valid-type]
        async with get_db() as conn:
            values = tuple(getattr(body, col) for col in create_columns)
            placeholders = ", ".join("?" for _ in create_columns)
            column_list = ", ".join(create_columns)
            conflict_value = getattr(body, conflict_field, None)
            conflict_detail = (
                f"{label} already exists: {conflict_value}"
                if conflict_value is not None
                else f"{label} already exists"
            )
            with integrity_guard(conflict_detail=conflict_detail):
                cursor = await conn.execute(
                    f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})",  # nosec B608 - table/columns from internal allow-list, not user input
                    values,
                )
                await conn.commit()
            return bool_fields(await get_or_404(conn, table, cursor.lastrowid, label), "active")

    @router.put(detail_prefix, response_model=response_model, name=f"update_{table}")
    async def update_item(item_id: int, body: update_model) -> dict:  # type: ignore[valid-type]
        async with get_db() as conn:
            existing = await get_or_404(conn, table, item_id, label)
            updates: dict[str, Any] = body.model_dump(exclude_unset=True)
            if not updates:
                return bool_fields(existing, "active")
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [item_id]
            with integrity_guard(conflict_detail=f"{label} name already exists"):
                await conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE id = ?",  # nosec B608 - table/columns from internal allow-list, not user input
                    values,
                )
                await conn.commit()
            return bool_fields(await get_or_404(conn, table, item_id, label), "active")

    @router.delete(detail_prefix, name=f"delete_{table}")
    async def delete_item(item_id: int) -> dict:
        async with get_db() as conn:
            await get_or_404(conn, table, item_id, label)
            await conn.execute(
                f"UPDATE {table} SET active = 0 WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                (item_id,),
            )
            await conn.commit()
        return {"ok": True}


def build_equipment_router(
    router: APIRouter,
    *,
    table: str,
    url_slug: str,
    label: str,
    create_model: type[BaseModel],
    update_model: type[BaseModel],
    response_model: type[BaseModel],
    response_builder: Callable[[Any, dict], Awaitable[dict]],
    name_column: str = "model_name",
    order_by: str | None = None,
    bool_columns: tuple[str, ...] = ("is_mine",),
    interface_junction: tuple[str, str] | None = None,
    update_conflict_detail: str | None = None,
    check_detail_fn: Callable[[dict], str] | None = None,
) -> None:
    """Register list / get / create / update / soft-delete / mine-toggle endpoints
    for a mid-complexity equipment table.

    Args:
        router: Router to attach endpoints to.
        table: SQL table name (e.g. ``"camera"``).
        url_slug: URL fragment (e.g. ``"filter-wheel"``).
        label: Human-readable label for errors (e.g. ``"Camera"``).
        create_model / update_model / response_model: Pydantic models.
        response_builder: ``async def (conn, row_dict) -> dict``; produces the
            full nested response shape. Required because nested joins differ
            per type.
        name_column: Identifier column referenced in conflict messages.
            ``"model_name"`` for hardware, ``"name"`` for software.
        order_by: SQL ORDER BY for list. Default: ``<name_column>``.
        bool_columns: Columns that are Python-bool in Pydantic but INTEGER(0/1)
            in SQL. Values are coerced via ``int(...)`` on INSERT/UPDATE.
        interface_junction: Optional ``(junction_table, fk_column)`` tuple.
            When set, ``interface_ids`` on the body rebuilds the M2M junction
            on create/update.
        update_conflict_detail: 409 detail for UPDATE. Default:
            ``f"{label} (manufacturer, {name_column}) already exists"``.
        check_detail_fn: Optional ``(body_dict) -> str`` to produce the 422
            detail when a CHECK constraint fires (e.g. ``software.category``).
    """
    if order_by is None:
        order_by = name_column
    if update_conflict_detail is None:
        update_conflict_detail = f"{label} (manufacturer, {name_column}) already exists"

    insert_columns = tuple(col for col in create_model.model_fields if col != "interface_ids")
    prefix = f"/{url_slug}"
    detail_prefix = f"/{url_slug}/{{item_id}}"
    mine_prefix = f"/{url_slug}/{{item_id}}/mine"

    def _coerce_bools(d: dict) -> None:
        for col in bool_columns:
            if col in d and d[col] is not None:
                d[col] = int(d[col])

    async def _rebuild_interfaces(conn, item_id: int, iface_ids: list[int]) -> None:
        if interface_junction is None:
            return
        junction_table, fk_column = interface_junction
        await conn.execute(
            f"DELETE FROM {junction_table} WHERE {fk_column} = ?",  # nosec B608 - table/columns from internal allow-list, not user input
            (item_id,),
        )
        if iface_ids:
            await conn.executemany(
                f"INSERT INTO {junction_table} ({fk_column}, interface_id) VALUES (?, ?)",  # nosec B608 - table/columns from internal allow-list, not user input
                [(item_id, i) for i in iface_ids],
            )

    @router.get(prefix, response_model=list[response_model], name=f"list_{table}")
    async def list_items(
        include_retired: bool = Query(False, description="Include retired items"),
        mine: bool = Query(False, description="Return only items marked as mine"),
    ) -> list[dict]:
        async with get_db() as conn:
            conditions: list[str] = []
            if not include_retired:
                conditions.append("active = 1")
            if mine:
                conditions.append("is_mine = 1")
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = await conn.execute(
                f"SELECT * FROM {table} {where} ORDER BY {order_by}"  # nosec B608 - table/columns from internal allow-list, not user input
            )
            return [await response_builder(conn, row_to_dict(r)) for r in await rows.fetchall()]

    @router.get(detail_prefix, response_model=response_model, name=f"get_{table}")
    async def get_item(item_id: int) -> dict:
        async with get_db() as conn:
            row = await get_or_404(conn, table, item_id, label)
            return await response_builder(conn, row)

    @router.post(prefix, response_model=response_model, status_code=201, name=f"create_{table}")
    async def create_item(body: create_model) -> dict:  # type: ignore[valid-type]
        async with get_db() as conn:
            values = []
            for col in insert_columns:
                v = getattr(body, col)
                if col in bool_columns and v is not None:
                    v = int(v)
                values.append(v)
            placeholders = ", ".join("?" for _ in insert_columns)
            column_list = ", ".join(insert_columns)
            conflict_value = getattr(body, name_column, None)
            guard_kwargs: dict[str, Any] = {
                "conflict_detail": f"{label} already exists: {conflict_value}"
                if conflict_value is not None
                else f"{label} already exists",
            }
            if check_detail_fn is not None:
                guard_kwargs["check_detail"] = check_detail_fn(body.model_dump())
            with integrity_guard(**guard_kwargs):
                cursor = await conn.execute(
                    f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})",  # nosec B608 - table/columns from internal allow-list, not user input
                    tuple(values),
                )
                item_id = cursor.lastrowid
                if interface_junction is not None:
                    iface_ids = getattr(body, "interface_ids", None) or []
                    await _rebuild_interfaces(conn, item_id, iface_ids)
                await conn.commit()
            row = await get_or_404(conn, table, item_id, label)
            return await response_builder(conn, row)

    @router.put(detail_prefix, response_model=response_model, name=f"update_{table}")
    async def update_item(item_id: int, body: update_model) -> dict:  # type: ignore[valid-type]
        async with get_db() as conn:
            existing = await get_or_404(conn, table, item_id, label)
            updates: dict[str, Any] = body.model_dump(exclude_unset=True)
            iface_ids = updates.pop("interface_ids", None)
            if not updates and iface_ids is None:
                return await response_builder(conn, existing)
            if updates:
                _coerce_bools(updates)
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                sql_values = list(updates.values()) + [item_id]
                guard_kwargs: dict[str, Any] = {"conflict_detail": update_conflict_detail}
                if check_detail_fn is not None:
                    guard_kwargs["check_detail"] = check_detail_fn(updates)
                with integrity_guard(**guard_kwargs):
                    await conn.execute(
                        f"UPDATE {table} SET {set_clause} WHERE id = ?",  # nosec B608 - table/columns from internal allow-list, not user input
                        sql_values,
                    )
            if iface_ids is not None and interface_junction is not None:
                await _rebuild_interfaces(conn, item_id, iface_ids)
            await conn.commit()
            row = await get_or_404(conn, table, item_id, label)
            return await response_builder(conn, row)

    @router.delete(detail_prefix, name=f"delete_{table}")
    async def delete_item(item_id: int) -> dict:
        async with get_db() as conn:
            await get_or_404(conn, table, item_id, label)
            await conn.execute(
                f"UPDATE {table} SET active = 0 WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                (item_id,),
            )
            await conn.commit()
        return {"ok": True}

    @router.post(mine_prefix, response_model=response_model, name=f"toggle_{table}_mine")
    async def toggle_mine(item_id: int, body: MineToggle) -> dict:
        async with get_db() as conn:
            await get_or_404(conn, table, item_id, label)
            await conn.execute(
                f"UPDATE {table} SET is_mine = ? WHERE id = ?",  # nosec B608 - table name from internal allow-list, not user input
                (int(body.is_mine), item_id),
            )
            await conn.commit()
            row = await get_or_404(conn, table, item_id, label)
            return await response_builder(conn, row)
