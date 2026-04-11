"""Settings API endpoints."""

from fastapi import APIRouter

from nightcrate.core.compute import set_gpu_enabled
from nightcrate.core.config import Settings, get_settings, update_settings

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("", response_model=Settings)
async def read_settings() -> Settings:
    return await get_settings()


@router.put("", response_model=Settings)
async def write_settings(payload: Settings) -> Settings:
    saved = await update_settings(payload)
    set_gpu_enabled(saved.gpu_acceleration)
    return saved
