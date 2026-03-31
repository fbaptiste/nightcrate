"""Settings API endpoints."""

from fastapi import APIRouter

from nightcrate.core.config import Settings, get_settings, update_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=Settings)
async def read_settings() -> Settings:
    return get_settings()


@router.put("", response_model=Settings)
async def write_settings(payload: Settings) -> Settings:
    return update_settings(payload)
