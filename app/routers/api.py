import json

from fastapi import APIRouter, Depends, File, HTTPException, Security, UploadFile
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.services.worldpop import (
    CoordinatesOutsideCountryError,
    GeoJSONOutsideCountryError,
    WorldPopService,
    count_geojson_vertices,
    normalize_iso3,
)
from app.dependencies import get_current_active_user
from app.models.models import User

bearer_scheme = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/api", tags=["API"])


def _format_byte_size(byte_count: int) -> str:
    megabyte = 1024 * 1024
    if byte_count % megabyte == 0:
        return f"{byte_count // megabyte:,}MB"
    if byte_count % 1024 == 0:
        return f"{byte_count // 1024:,}KB"
    return f"{byte_count:,} bytes"


@router.get("/pop")
async def get_pop(
    iso3: str,
    lat: float,
    lon: float,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    _credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)
):
    try:
        iso3 = normalize_iso3(iso3)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    service = WorldPopService(db)
    try:
        pop = await service.get_pop(iso3, lat, lon)
        return {"pop": pop}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pop-radius")
async def get_pop_radius(
    iso3: str,
    lat: float,
    lon: float,
    radius: float,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    _credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)
):
    try:
        iso3 = normalize_iso3(iso3)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not settings.POP_RADIUS_MIN_METERS <= radius <= settings.POP_RADIUS_MAX_METERS:
        minimum = settings.POP_RADIUS_MIN_METERS
        maximum = settings.POP_RADIUS_MAX_METERS
        raise HTTPException(
            status_code=422,
            detail=(
                f"radius must be between {minimum:g} and {maximum:g} metres "
                f"({maximum / 1000:g} km)."
            ),
        )
    service = WorldPopService(db)
    try:
        pop = await service.get_pop_radius(iso3, lat, lon, radius)
        return {"pop": pop}
    except CoordinatesOutsideCountryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pop-shape")
async def get_pop_shape(
    iso3: str,
    geojson_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    _credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)
):
    try:
        iso3 = normalize_iso3(iso3)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

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
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="geojson file must contain valid JSON")

    if not isinstance(geojson, dict):
        raise HTTPException(status_code=422, detail="geojson file must contain a JSON object")

    if count_geojson_vertices(geojson) > settings.GEOJSON_MAX_VERTICES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"geojson must contain {settings.GEOJSON_MAX_VERTICES:,} "
                "vertices or fewer"
            ),
        )

    service = WorldPopService(db)
    try:
        pop = await service.get_pop_shape(iso3, geojson)
        return {"pop": pop}
    except GeoJSONOutsideCountryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
