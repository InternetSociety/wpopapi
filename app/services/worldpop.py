import asyncio
import logging
import math
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import numpy as np
import pyproj
import rasterio
from rasterio.errors import WindowError
from app.config import dataset, release, settings, version, year
from app.models.models import CachedTile
from app.repositories.tiles import TileRepository
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from shapely.geometry import GeometryCollection, Point, mapping, shape
from shapely.geometry import box
from shapely.ops import transform
from sqlalchemy.ext.asyncio import AsyncSession


class CoordinatesOutsideCountryError(ValueError):
    pass


class GeoJSONOutsideCountryError(ValueError):
    def __init__(self, iso3: str):
        super().__init__(f"geojson is not inside the bounds of country {iso3}")


class TileNotFoundError(ValueError):
    def __init__(self, iso3: str):
        super().__init__(f"no tile available for country {iso3}")


def normalize_iso3(iso3: str) -> str:
    normalized = iso3.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("iso3 must be a three-letter ISO country code")
    return normalized


def parse_iso3_csv(iso3_csv: str) -> list[str]:
    iso3_codes: list[str] = []
    seen: set[str] = set()

    for raw_code in iso3_csv.split(","):
        code = raw_code.strip()
        if not code:
            continue
        normalized = normalize_iso3(code)
        if normalized in seen:
            continue
        seen.add(normalized)
        iso3_codes.append(normalized)

    if not iso3_codes:
        raise ValueError(
            "iso3 list must contain at least one valid three-letter ISO country code"
        )

    return iso3_codes


def get_worldpop_url(iso3: str) -> str:
    iso3 = normalize_iso3(iso3)
    file_name = f"{iso3.lower()}_pop_{year}_CN_100m_{release}_{version}.tif"
    return (
        "https://data.worldpop.org/GIS/Population/"
        f"{dataset}/{release}/{year}/{iso3}/{version}/100m/constrained/{file_name}"
    )


def count_geojson_vertices(obj: Any) -> int:
    if not isinstance(obj, dict):
        return 0

    geo_type = obj.get("type")
    if geo_type == "FeatureCollection":
        features = obj.get("features", [])
        if not isinstance(features, list):
            return 0
        return sum(count_geojson_vertices(feature) for feature in features)

    if geo_type == "Feature":
        return count_geojson_vertices(obj.get("geometry"))

    return _count_coordinate_vertices(obj.get("coordinates"))


def _count_coordinate_vertices(value: Any) -> int:
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(item, (int, float)) for item in value):
            return 1
        return sum(_count_coordinate_vertices(item) for item in value)
    return 0


def _extract_geometries(geojson: dict) -> list[Any]:
    geo_type = geojson.get("type")
    if geo_type == "FeatureCollection":
        geometries: list[Any] = []
        for feature in geojson.get("features", []):
            if isinstance(feature, dict) and feature.get("geometry"):
                geometries.extend(_extract_geometries(feature["geometry"]))
        return geometries

    if geo_type == "Feature":
        geometry = geojson.get("geometry")
        if not isinstance(geometry, dict):
            return []
        return _extract_geometries(geometry)

    return [shape(geojson)]


def _point_within_bounds(bounds: Any, lon: float, lat: float) -> bool:
    minx, miny, maxx, maxy = bounds
    return minx <= lon <= maxx and miny <= lat <= maxy


class WorldPopService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = TileRepository(db)

    async def get_tile_path(self, iso3: str, skip_missing: bool = False) -> str:
        iso3 = normalize_iso3(iso3)

        cached_tile = await self.repository.get_by_tile_id(iso3)

        now = datetime.now(UTC)
        expires_at = now + timedelta(days=settings.TILE_CACHE_EXPIRY_DAYS)

        if cached_tile:
            cached_tile.last_used_at = now
            cached_tile.expires_at = expires_at
            await self.repository.flush()
            return cached_tile.file_path

        return await self._download_and_cache_tile(
            iso3, now, expires_at, skip_missing=skip_missing
        )

    async def list_cached_tiles(self) -> list[CachedTile]:
        return await self.repository.list_all()

    async def fill_tile_cache(self, iso3_csv: str) -> list[str]:
        iso3_codes = parse_iso3_csv(iso3_csv)
        cached_tiles: list[str] = []

        for iso3 in iso3_codes:
            try:
                cached_tiles.append(await self.get_tile_path(iso3, skip_missing=True))
            except TileNotFoundError:
                logging.info("Skipping missing tile %s during cache fill", iso3)

        return cached_tiles

    async def _download_and_cache_tile(
        self,
        iso3: str,
        now: datetime,
        expires_at: datetime,
        skip_missing: bool = False,
    ) -> str:
        url = get_worldpop_url(iso3)
        file_name = os.path.basename(url)
        file_path = os.path.join(settings.TILE_CACHE_DIR, file_name)

        logging.info("Downloading tile %s from %s", iso3, url)
        async with httpx.AsyncClient(
            timeout=settings.TILE_DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                if skip_missing and response.status_code == 404:
                    raise TileNotFoundError(iso3)
                raise Exception(
                    f"Failed to download tile {iso3} from {url}: {response.status_code}"
                )
            await asyncio.to_thread(_write_bytes, file_path, response.content)
            logging.info("Completed download of tile %s to %s", iso3, file_path)

        new_tile = CachedTile(
            tile_id=iso3,
            file_path=file_path,
            last_used_at=now,
            expires_at=expires_at,
        )
        self.repository.add(new_tile)
        await self.repository.flush()

        expired_tiles = await self.repository.list_expired(now)
        for expired_tile in expired_tiles:
            await asyncio.to_thread(_remove_if_present, expired_tile.file_path)
            await self.repository.delete(expired_tile)
        await self.repository.flush()

        return file_path

    async def get_pop(self, iso3: str, lat: float, lon: float) -> int:
        logging.info("get_pop: iso3=%s lat=%s lon=%s", iso3, lat, lon)
        file_path = await self.get_tile_path(iso3)
        return await asyncio.to_thread(_sample_population, file_path, lat, lon)

    async def get_pop_radius(
        self, iso3: str, lat: float, lon: float, radius_meters: float
    ) -> int:
        logging.info(
            "get_pop_radius: iso3=%s lat=%s lon=%s radius=%s",
            iso3,
            lat,
            lon,
            radius_meters,
        )
        file_path = await self.get_tile_path(iso3)
        within_bounds = await asyncio.to_thread(
            _coordinates_within_raster, file_path, lat, lon
        )
        if not within_bounds:
            raise CoordinatesOutsideCountryError(
                "coordinates supplied are outside of the country specified"
            )

        aeqd_proj = pyproj.Proj(
            proj="aeqd", ellps="WGS84", datum="WGS84", lat_0=lat, lon_0=lon
        )
        wgs84_proj = pyproj.Proj(proj="latlong", datum="WGS84")
        project_to_wgs84 = pyproj.Transformer.from_proj(
            aeqd_proj, wgs84_proj, always_xy=True
        ).transform
        buffer_wgs84 = transform(project_to_wgs84, Point(0, 0).buffer(radius_meters))
        return await self._sum_population_within_geometry(iso3, [buffer_wgs84])

    async def get_pop_shape(self, iso3: str, geojson: dict) -> int:
        geometries = _extract_geometries(geojson)
        if not geometries:
            return 0
        logging.info("get_pop_shape: iso3=%s geometries=%s", iso3, len(geometries))
        file_path = await self.get_tile_path(iso3)
        intersects = await asyncio.to_thread(
            _geometries_intersect_raster, file_path, geometries
        )
        if not intersects:
            raise GeoJSONOutsideCountryError(normalize_iso3(iso3))
        return await self._sum_population_within_geometry(iso3, geometries)

    async def _sum_population_within_geometry(
        self, iso3: str, geometries: list[Any]
    ) -> int:
        file_path = await self.get_tile_path(iso3)
        return await asyncio.to_thread(_sum_raster_population, file_path, geometries)


def _write_bytes(file_path: str, content: bytes) -> None:
    with open(file_path, "wb") as output:
        output.write(content)


def _remove_if_present(file_path: str) -> None:
    if os.path.exists(file_path):
        os.remove(file_path)


def _sample_population(file_path: str, lat: float, lon: float) -> int:
    with rasterio.open(file_path) as src:
        sample = next(src.sample([(lon, lat)], masked=True))
        value = sample[0]
        if np.ma.is_masked(value):
            return 0
        return int(round(float(value)))


def _coordinates_within_raster(file_path: str, lat: float, lon: float) -> bool:
    with rasterio.open(file_path) as src:
        return _point_within_bounds(src.bounds, lon, lat)


def _geometries_intersect_raster(file_path: str, geometries: list[Any]) -> bool:
    with rasterio.open(file_path) as src:
        tile_bounds = box(*src.bounds)
        return any(geometry.intersects(tile_bounds) for geometry in geometries)


def _sum_raster_population(file_path: str, geometries: list[Any]) -> int:
    with rasterio.open(file_path) as src:
        minx, miny, maxx, maxy = GeometryCollection(geometries).bounds
        if any(math.isinf(value) for value in (minx, miny, maxx, maxy)):
            return 0
        window = from_bounds(minx, miny, maxx, maxy, src.transform)
        try:
            window = window.intersection(
                rasterio.windows.Window(0, 0, src.width, src.height)
            )
        except WindowError:
            return 0
        if window.width <= 0 or window.height <= 0:
            return 0
        window_data = src.read(1, window=window, masked=True)
        if window_data.size == 0:
            return 0
        geom_mask = geometry_mask(
            [mapping(geometry) for geometry in geometries],
            transform=src.window_transform(window),
            invert=True,
            out_shape=window_data.shape,
        )
        valid_mask = geom_mask & ~np.ma.getmaskarray(window_data)
        if not valid_mask.any():
            return 0
        return int(round(float(window_data.data[valid_mask].sum())))
