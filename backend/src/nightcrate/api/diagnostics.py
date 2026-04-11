"""Activity Console: in-memory request tracking for latency analysis."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send

router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics"])

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

MAX_RECORDS = 5000


@dataclass
class RequestRecord:
    timestamp: str
    method: str
    path: str
    query: str
    status_code: int
    duration_ms: float
    activity: str | None


_records: deque[RequestRecord] = deque(maxlen=MAX_RECORDS)

# ---------------------------------------------------------------------------
# Middleware — pure ASGI (no BaseHTTPMiddleware serialization)
# ---------------------------------------------------------------------------

_SKIP_PREFIXES = ("/api/diagnostics",)


class RequestTrackingMiddleware:
    """Record every request with timing and optional activity label.

    Implemented as a raw ASGI middleware to avoid the request-serialization
    behaviour of Starlette's BaseHTTPMiddleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Extract activity label from headers or query string
        headers = dict(scope.get("headers", []))
        activity = headers.get(b"x-activity", b"").decode() or None
        if not activity:
            qs = scope.get("query_string", b"").decode()
            activity = _parse_activity_from_qs(qs)

        # Capture status code from the response start message
        status_code = 0
        start = time.perf_counter()
        start_time = datetime.now(UTC)

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            _records.append(
                RequestRecord(
                    timestamp=start_time.isoformat(timespec="milliseconds"),
                    method=scope["method"],
                    path=path,
                    query=scope.get("query_string", b"").decode(),
                    status_code=status_code,
                    duration_ms=round(duration_ms, 1),
                    activity=activity,
                )
            )


def _parse_activity_from_qs(qs: str) -> str | None:
    """Extract _activity param without pulling in urllib for every request."""
    for part in qs.split("&"):
        if part.startswith("_activity="):
            from urllib.parse import unquote_plus

            return unquote_plus(part[10:])
    return None


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------


class RequestRecordOut(BaseModel):
    timestamp: str
    method: str
    path: str
    query: str
    status_code: int
    duration_ms: float


class ActivityGroup(BaseModel):
    activity: str
    requests: list[RequestRecordOut] = field(default_factory=list)
    total_duration_ms: float = 0.0


class ActivityResponse(BaseModel):
    groups: list[ActivityGroup]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/activity", response_model=ActivityResponse)
async def get_activity() -> ActivityResponse:
    """Return tracked requests grouped by consecutive activity label."""
    groups: list[ActivityGroup] = []
    current_label: str | None = None
    current_group: ActivityGroup | None = None

    for rec in _records:
        label = rec.activity or "(no activity)"
        if label != current_label or current_group is None:
            current_label = label
            current_group = ActivityGroup(activity=label)
            groups.append(current_group)
        current_group.requests.append(
            RequestRecordOut(
                timestamp=rec.timestamp,
                method=rec.method,
                path=rec.path,
                query=rec.query,
                status_code=rec.status_code,
                duration_ms=rec.duration_ms,
            )
        )
        current_group.total_duration_ms = round(
            current_group.total_duration_ms + rec.duration_ms, 1
        )

    return ActivityResponse(groups=groups)


@router.delete("/activity")
async def clear_activity() -> dict:
    """Clear all tracked request records."""
    _records.clear()
    return {"cleared": True}
