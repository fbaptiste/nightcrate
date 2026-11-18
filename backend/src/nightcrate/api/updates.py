"""Application update preferences, checks, and computed notices."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from nightcrate.catalog_loader import remote
from nightcrate.catalog_loader.mgc50_fetch import read_installed_fetch
from nightcrate.catalog_loader.registry import read_installed_version, user_catalogs_root
from nightcrate.catalog_loader.wikidata import QUERY_VERSION
from nightcrate.catalog_loader.wikidata import read_installed_version as read_wikidata
from nightcrate.core import runtime
from nightcrate.core.updates_state import UpdatesState, load_updates_state, save_updates_state
from nightcrate.services import update_check
from nightcrate.services.update_notices import (
    AGE_REMINDER_DAYS,
    LATER_HOURS,
    CatalogInstall,
    Notice,
    NoticeId,
    compute_notices,
    is_check_due,
)

router = APIRouter(prefix="/api/updates", tags=["Updates"])

_state_lock = asyncio.Lock()
_single_flight_lock = asyncio.Lock()
_check_task: asyncio.Task[None] | None = None


class UpdatesStatus(BaseModel):
    check_automatically: bool | None
    install_kind: runtime.InstallKind
    current_version: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    check_due: bool
    skipped_version: str | None
    notices: list[Notice]
    updated_from: str | None
    backup_taken: bool


class PreferencesRequest(BaseModel):
    check_automatically: bool


class NoticeActionRequest(BaseModel):
    action: Literal["later", "skip", "remind"]


def _now() -> datetime:
    return datetime.now(UTC)


def _datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _catalogs() -> CatalogInstall:
    root = user_catalogs_root()
    mgc50 = read_installed_fetch(root)
    wikidata = read_wikidata(root)
    return CatalogInstall(
        openngc_tag=read_installed_version(root),
        mgc50_fetched_at=_datetime(mgc50.get("fetched_at")),
        wikidata_fetched_at=_datetime(wikidata.get("fetched_at")),
        wikidata_query_outdated=(
            wikidata.get("fetched_at") is not None
            and wikidata.get("query_version") != QUERY_VERSION
        ),
    )


def _status(state: UpdatesState, now: datetime | None = None) -> UpdatesStatus:
    now = now or _now()
    current_version = runtime.app_version()
    return UpdatesStatus(
        check_automatically=state.check_automatically,
        install_kind=runtime.install_kind,
        current_version=current_version,
        last_attempt_at=state.last_attempt_at,
        last_success_at=state.last_success_at,
        last_error=state.last_error,
        check_due=is_check_due(state, now),
        skipped_version=state.skipped_app_version,
        notices=compute_notices(
            state,
            _catalogs(),
            current_version=current_version,
            install_kind=runtime.install_kind,
            platform_key=update_check.platform_key(),
            now=now,
        ),
        updated_from=(
            state.last_run_version
            if state.last_run_version is not None and state.last_run_version != current_version
            else None
        ),
        backup_taken=runtime.last_activation_backup is not None,
    )


async def record_first_run_version() -> None:
    """Record the first version ever run without replacing an existing value."""
    async with _state_lock:
        state = load_updates_state()
        if state.last_run_version is None:
            state.last_run_version = runtime.app_version()
            save_updates_state(state)


@router.get("", response_model=UpdatesStatus)
async def get_updates() -> UpdatesStatus:
    return _status(load_updates_state())


async def _perform_check() -> None:
    attempted_at = _now()
    openngc_installed = read_installed_version(user_catalogs_root())
    app_result, openngc_result = await asyncio.gather(
        update_check.fetch_latest_app(),
        remote.fetch_latest_release() if openngc_installed else asyncio.sleep(0, result=None),
        return_exceptions=True,
    )
    errors: list[str] = []
    if isinstance(app_result, BaseException):
        errors.append(str(app_result) or "couldn't reach GitHub")
    if isinstance(openngc_result, BaseException):
        errors.append("couldn't reach GitHub")

    async with _state_lock:
        # Reload after network I/O so preference/dismiss changes made meanwhile survive.
        state = load_updates_state()
        state.last_attempt_at = attempted_at
        if not isinstance(app_result, BaseException):
            state.latest_app = app_result
        if openngc_installed and not isinstance(openngc_result, BaseException):
            state.latest_openngc_tag = openngc_result.tag_name if openngc_result else None
        state.last_error = "; ".join(dict.fromkeys(errors)) if errors else None
        if not errors:
            state.last_success_at = attempted_at
        save_updates_state(state)


async def _shared_check() -> None:
    global _check_task
    async with _single_flight_lock:
        if _check_task is None or _check_task.done():
            _check_task = asyncio.create_task(_perform_check())
        task = _check_task
    await asyncio.shield(task)


async def drain_background_fetches() -> None:
    """Cancel and await the update check present when draining starts."""
    global _check_task
    task = _check_task
    if task is None:
        return
    if not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    if _check_task is task:
        _check_task = None


@router.post("/check", response_model=UpdatesStatus)
async def check_updates() -> UpdatesStatus:
    await _shared_check()
    return _status(load_updates_state())


@router.patch("/preferences", response_model=UpdatesStatus)
async def set_preferences(request: PreferencesRequest) -> UpdatesStatus:
    async with _state_lock:
        state = load_updates_state()
        state.check_automatically = request.check_automatically
        save_updates_state(state)
    return _status(state)


@router.post("/notices/{notice_id}", response_model=UpdatesStatus)
async def act_on_notice(notice_id: NoticeId, request: NoticeActionRequest) -> UpdatesStatus:
    allowed = {
        "app": {"later", "skip"},
        "openngc": {"skip"},
        "mgc50_age": {"remind"},
        "wikidata_age": {"remind"},
        "wikidata_query": {"remind"},
    }
    if request.action not in allowed[notice_id]:
        raise HTTPException(status_code=422, detail="That action is not valid for this notice.")
    now = _now()
    async with _state_lock:
        state = load_updates_state()
        if notice_id == "app" and request.action == "later":
            state.app_later_until = now + timedelta(hours=LATER_HOURS)
        elif notice_id == "app":
            state.skipped_app_version = state.latest_app.version if state.latest_app else None
        elif notice_id == "openngc":
            state.skipped_openngc_release = state.latest_openngc_tag
        else:
            state.remind_after[notice_id] = now + timedelta(days=AGE_REMINDER_DAYS)
        save_updates_state(state)
    return _status(state, now)


@router.delete("/skipped-version", status_code=status.HTTP_204_NO_CONTENT)
async def clear_skipped_version() -> Response:
    async with _state_lock:
        state = load_updates_state()
        state.skipped_app_version = None
        save_updates_state(state)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/seen-version", status_code=status.HTTP_204_NO_CONTENT)
async def seen_version() -> Response:
    async with _state_lock:
        state = load_updates_state()
        state.last_run_version = runtime.app_version()
        save_updates_state(state)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
