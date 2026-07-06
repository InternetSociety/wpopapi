import json

from fastapi import APIRouter, Depends, File, HTTPException, Security, UploadFile
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
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

    if radius <= 0 or radius > 100_000:
        raise HTTPException(status_code=422, detail="radius must be between 1 and 100000 metres (100 km).")
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

    body = await geojson_file.read()
    if len(body) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="geojson body must be 5MB or smaller")

    try:
        geojson = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="geojson file must contain valid JSON")

    if not isinstance(geojson, dict):
        raise HTTPException(status_code=422, detail="geojson file must contain a JSON object")

    if count_geojson_vertices(geojson) > 10_000:
        raise HTTPException(status_code=422, detail="geojson must contain 10,000 vertices or fewer")

    service = WorldPopService(db)
    try:
        pop = await service.get_pop_shape(iso3, geojson)
        return {"pop": pop}
    except GeoJSONOutsideCountryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
