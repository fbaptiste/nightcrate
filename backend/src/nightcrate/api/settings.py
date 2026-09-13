"""Settings API endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from nightcrate.core.compute import gpu_backend_name, set_gpu_enabled
from nightcrate.core.config import Settings, get_settings, update_settings

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


@router.get("/compute", response_model=ComputeInfo)
async def read_compute_info() -> ComputeInfo:
    """Report the GPU backend available to this process.

    Availability only — this deliberately ignores the user's gpu_acceleration
    preference, which the client already holds. Kept off the Settings model
    because PUT /api/settings persists every field on it into the KV table.
    """
    return ComputeInfo(gpu_backend=gpu_backend_name())
