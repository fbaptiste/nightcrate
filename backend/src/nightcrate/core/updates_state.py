"""Durable application-wide update preferences and check results."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, field_validator

from nightcrate.core import app_config


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return value


class LatestApp(BaseModel):
    version: str
    release_version: str | None = None
    published_at: datetime | None = None
    notes: list[str] = []
    release_url: str
    platforms: list[str] = []
    min_os: dict[str, str] = {}

    _published_is_aware = field_validator("published_at")(_aware)


class UpdatesState(BaseModel):
    check_automatically: bool | None = None
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    latest_app: LatestApp | None = None
    latest_openngc_tag: str | None = None
    skipped_app_version: str | None = None
    app_later_until: datetime | None = None
    skipped_openngc_release: str | None = None
    remind_after: dict[str, datetime] = {}
    last_run_version: str | None = None

    _times_are_aware = field_validator("last_attempt_at", "last_success_at", "app_later_until")(
        _aware
    )

    @field_validator("remind_after")
    @classmethod
    def _reminders_are_aware(cls, value: dict[str, datetime]) -> dict[str, datetime]:
        for item in value.values():
            _aware(item)
        return value


def _path() -> Path:
    return app_config.APP_DIR / "updates.json"


def load_updates_state() -> UpdatesState:
    """Load valid fields independently; corrupt fields retain their defaults."""
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return UpdatesState()
    if not isinstance(raw, dict):
        return UpdatesState()

    valid: dict[str, object] = {}
    for name, field in UpdatesState.model_fields.items():
        if name not in raw:
            continue
        try:
            # Validate one field at a time so one value cannot discard the rest.
            value = TypeAdapter(field.annotation).validate_python(raw[name])
            UpdatesState(**{name: value})
        except TypeError, ValueError:
            continue
        valid[name] = value
    return UpdatesState(**valid)


def save_updates_state(state: UpdatesState) -> None:
    """Atomically replace ``updates.json`` with a complete state document."""
    destination = _path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".updates-", suffix=".json", dir=destination.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(state.model_dump_json(indent=2))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, destination)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
