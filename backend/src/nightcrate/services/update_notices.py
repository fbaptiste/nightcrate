"""Pure update and catalog-notice rules."""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from nightcrate.core.runtime import InstallKind
from nightcrate.core.updates_state import UpdatesState

AGE_REMINDER_DAYS = 183
LATER_HOURS = 24
CHECK_INTERVAL_HOURS = 24
MACOS_VERSION_UNAVAILABLE = "This update can't be checked against this Mac's system version."

NoticeId = Literal["app", "openngc", "mgc50_age", "wikidata_age", "wikidata_query"]


@dataclass(frozen=True, slots=True)
class CatalogInstall:
    openngc_tag: str | None = None
    mgc50_fetched_at: datetime | None = None
    wikidata_fetched_at: datetime | None = None
    wikidata_query_outdated: bool = False


class Notice(BaseModel):
    id: NoticeId
    version: str | None = None
    current_version: str | None = None
    published_at: datetime | None = None
    notes: list[str] = Field(default_factory=list, max_length=4)
    release_url: str | None = None
    installable: bool = False
    install_blocked: str | None = None
    latest_tag: str | None = None
    installed_tag: str | None = None
    downloaded_at: datetime | None = None


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(map(int, match.groups())) if match else None  # type: ignore[return-value]


def _os_version(text: str) -> tuple[int, ...] | None:
    if not re.fullmatch(r"\d+(?:\.\d+)*", text):
        return None
    return tuple(int(part) for part in text.split("."))


def _older_version(current: tuple[int, ...], required: tuple[int, ...]) -> bool:
    length = max(len(current), len(required))
    return current + (0,) * (length - len(current)) < required + (0,) * (length - len(required))


def _macos_install_blocked(latest_min_os: dict[str, str], platform_key: str | None) -> str | None:
    if platform_key is None or not platform_key.startswith("darwin-"):
        return None
    if platform_key not in latest_min_os:
        return None
    required_text = latest_min_os[platform_key]
    required = _os_version(required_text)
    if required is None:
        return MACOS_VERSION_UNAVAILABLE
    current_text = platform.mac_ver()[0]
    current = _os_version(current_text)
    if current is not None and not _older_version(current, required):
        return None
    display = list(required)
    while len(display) > 1 and display[-1] == 0:
        display.pop()
    return f"This update needs macOS {'.'.join(map(str, display))} or later."


def parse_notes(body: str) -> list[str]:
    notes: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("- ", "* ")):
            continue
        notes.append(stripped[2:].replace("**", ""))
        if len(notes) == 4:
            break
    return notes


def is_check_due(state: UpdatesState, now: datetime) -> bool:
    return state.check_automatically is True and (
        state.last_attempt_at is None
        or now - state.last_attempt_at >= timedelta(hours=CHECK_INTERVAL_HOURS)
    )


def _reminder_due(state: UpdatesState, notice_id: NoticeId, now: datetime) -> bool:
    until = state.remind_after.get(notice_id)
    return until is None or now >= until


def compute_notices(
    state: UpdatesState,
    catalogs: CatalogInstall,
    *,
    current_version: str,
    install_kind: InstallKind,
    platform_key: str | None,
    now: datetime,
) -> list[Notice]:
    notices: list[Notice] = []
    latest = state.latest_app
    latest_version = parse_version(latest.version) if latest else None
    current = parse_version(current_version)
    if (
        latest
        and latest_version is not None
        and current is not None
        and latest_version > current
        and latest.version != state.skipped_app_version
        and (state.app_later_until is None or now >= state.app_later_until)
        and (install_kind == "source" or platform_key in latest.platforms)
    ):
        platform_present = platform_key is not None and platform_key in latest.platforms
        install_blocked = _macos_install_blocked(latest.min_os, platform_key)
        notices.append(
            Notice(
                id="app",
                version=latest.version,
                current_version=current_version,
                published_at=latest.published_at,
                notes=latest.notes[:4],
                release_url=latest.release_url,
                install_blocked=install_blocked,
                installable=(
                    install_kind == "installed"
                    and platform_present
                    and latest.version == latest.release_version
                    and install_blocked is None
                ),
            )
        )

    if (
        catalogs.openngc_tag
        and state.latest_openngc_tag
        and catalogs.openngc_tag != state.latest_openngc_tag
        and state.latest_openngc_tag != state.skipped_openngc_release
    ):
        notices.append(
            Notice(
                id="openngc",
                latest_tag=state.latest_openngc_tag,
                installed_tag=catalogs.openngc_tag,
            )
        )

    cutoff = timedelta(days=AGE_REMINDER_DAYS)
    for notice_id, downloaded_at in (
        ("mgc50_age", catalogs.mgc50_fetched_at),
        ("wikidata_age", catalogs.wikidata_fetched_at),
    ):
        if downloaded_at and now - downloaded_at >= cutoff and _reminder_due(state, notice_id, now):
            notices.append(Notice(id=notice_id, downloaded_at=downloaded_at))

    if (
        catalogs.wikidata_fetched_at
        and catalogs.wikidata_query_outdated
        and _reminder_due(state, "wikidata_query", now)
    ):
        notices.append(Notice(id="wikidata_query", downloaded_at=catalogs.wikidata_fetched_at))
    return notices
