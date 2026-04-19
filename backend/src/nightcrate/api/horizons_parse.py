"""Stateless horizon-file parse endpoint.

The editor's staged-save flow needs to parse a horizon file into
(azimuth, altitude) points *without* writing anything to the DB. The
result is held in the Location editor's local state until the user
commits the outer Save. The existing ``POST /api/locations/{id}/horizon/import``
endpoint couples parsing with persistence; this endpoint decouples them.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from nightcrate.api.horizon_models import HorizonParseResponse, HorizonPointModel
from nightcrate.api.horizons import parse_upload_file

router = APIRouter(prefix="/api/horizons", tags=["Horizons"])


@router.post("/parse", response_model=HorizonParseResponse)
async def parse_horizon(file: UploadFile = File(...)) -> HorizonParseResponse:
    """Parse a horizon file and return the points + warnings without
    touching the database."""
    result = await parse_upload_file(file)
    return HorizonParseResponse(
        points=[HorizonPointModel(azimuth_deg=az, altitude_deg=alt) for az, alt in result.points],
        warnings=result.warnings,
        source_filename=result.source_filename,
    )
