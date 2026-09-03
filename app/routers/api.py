import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Security, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.dependencies import get_current_active_user, get_worldpop_service
from app.models.models import User
from app.schemas.schemas import PopulationResponse
from app.services.worldpop import WorldPopService


bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")
router = APIRouter(prefix="/api", tags=["API"])


def _format_byte_size(byte_count: int) -> str:
    megabyte = 1024 * 1024
    if byte_count % megabyte == 0:
        return f"{byte_count // megabyte:,}MB"
    if byte_count % 1024 == 0:
        return f"{byte_count // 1024:,}KB"
    return f"{byte_count:,} bytes"


@router.get("/pop", response_model=PopulationResponse)
async def get_pop(
    iso3: str,
    lat: float,
    lon: float,
    service: Annotated[WorldPopService, Depends(get_worldpop_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer_scheme)
    ],
) -> PopulationResponse:
    pop = await service.get_pop(iso3, lat, lon)
    return PopulationResponse(pop=pop)


@router.get("/pop-radius", response_model=PopulationResponse)
async def get_pop_radius(
    iso3: str,
    lat: float,
    lon: float,
    radius: float,
    service: Annotated[WorldPopService, Depends(get_worldpop_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer_scheme)
    ],
) -> PopulationResponse:
    pop = await service.get_pop_radius(iso3, lat, lon, radius)
    return PopulationResponse(pop=pop)


@router.post("/pop-shape", response_model=PopulationResponse)
async def get_pop_shape(
    iso3: str,
    geojson_file: Annotated[UploadFile, File()],
    service: Annotated[WorldPopService, Depends(get_worldpop_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer_scheme)
    ],
) -> PopulationResponse:
    body = await geojson_file.read(settings.GEOJSON_MAX_SIZE_BYTES + 1)
    if len(body) > settings.GEOJSON_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "geojson body must be "
                f"{_format_byte_size(settings.GEOJSON_MAX_SIZE_BYTES)} or smaller"
            ),
        )
    try:
        geojson = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=422, detail="geojson file must contain valid JSON"
        ) from exc
    if not isinstance(geojson, dict):
        raise HTTPException(
            status_code=422,
            detail="geojson file must contain a JSON object",
        )
    pop = await service.get_pop_shape(iso3, geojson)
    return PopulationResponse(pop=pop)
