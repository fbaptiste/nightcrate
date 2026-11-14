"""Settings API endpoints."""

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from nightcrate.core.compute import gpu_backend_name, set_gpu_enabled
from nightcrate.core.config import (
    Settings,
    SettingsPatchError,
    get_settings,
    update_settings,
    update_settings_partial,
)

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class ComputeInfo(BaseModel):
    """Which GPU backend this process can actually use, if any."""

    gpu_backend: str | None = None


@router.get("", response_model=Settings)
async def read_settings() -> Settings:
    return await get_settings()


@router.put("", response_model=Settings)
async def write_settings(payload: Settings) -> Settings:
    saved = await update_settings(payload)
    set_gpu_enabled(saved.gpu_acceleration)
    return saved


@router.patch("", response_model=Settings)
async def patch_settings(patch: dict[str, Any] = Body(...)) -> Settings:
    try:
        saved = await update_settings_partial(patch)
    except SettingsPatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "gpu_acceleration" in patch:
        set_gpu_enabled(saved.gpu_acceleration)
    return saved


@router.get("/compute", response_model=ComputeInfo)
async def read_compute_info() -> ComputeInfo:
    """Report the GPU backend available to this process.

    Availability only — this deliberately ignores the user's gpu_acceleration
    preference, which the client already holds. Kept off the Settings model
    because PUT /api/settings persists every field on it into the KV table.
    """
    return ComputeInfo(gpu_backend=gpu_backend_name())
