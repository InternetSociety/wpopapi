import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.config import dataset, release, version, year
from app.services.worldpop import (
    CoordinatesOutsideCountryError,
    GeoJSONOutsideCountryError,
    WorldPopService,
    TileNotFoundError,
    count_geojson_vertices,
    get_worldpop_url,
    normalize_iso3,
    parse_iso3_csv,
)


def _write_test_raster(path):
    data = np.arange(1, 101, dtype=np.int16).reshape((10, 10))
    transform = from_origin(0, 10, 1, 1)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data, 1)


def test_url_generation():
    assert get_worldpop_url("nzl") == (
        "https://data.worldpop.org/GIS/Population/"
        f"{dataset}/{release}/{year}/NZL/{version}/100m/constrained/"
        f"nzl_pop_{year}_CN_100m_{release}_{version}.tif"
    )


def test_normalize_iso3():
    assert normalize_iso3("nzl") == "NZL"


def test_parse_iso3_csv_normalizes_and_deduplicates():
    assert parse_iso3_csv("aus, nzl, AUS,usa") == ["AUS", "NZL", "USA"]


def test_parse_iso3_csv_rejects_empty_input():
    with pytest.raises(
        ValueError,
        match="iso3 list must contain at least one valid three-letter ISO country code",
    ):
        parse_iso3_csv(" , ")


def test_vertex_count():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                },
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0, 0], [1, 1], [2, 2]],
                },
            },
        ],
    }

    assert count_geojson_vertices(geojson) == 7


@pytest.mark.asyncio
async def test_pop_queries_with_local_raster(tmp_path):
    raster_path = tmp_path / "NZL_pop.tif"
    _write_test_raster(raster_path)

    service = WorldPopService(db=object())

    async def fake_get_tile_path(_iso3):
        return str(raster_path)

    service.get_tile_path = fake_get_tile_path  # type: ignore[method-assign]

    assert await service.get_pop("nzl", 7.5, 2.5) == 23
    assert await service.get_pop_radius("nzl", 7.5, 2.5, 2_000_000) == 5050
    with pytest.raises(
        CoordinatesOutsideCountryError,
        match="coordinates supplied are outside of the country specified",
    ):
        await service.get_pop_radius("nzl", -80.0, 170.0, 10_000)

    geojson = {
        "type": "Polygon",
        "coordinates": [[[0, 10], [2, 10], [2, 8], [0, 8], [0, 10]]],
    }
    assert await service.get_pop_shape("nzl", geojson) == 26

    outside_geojson = {
        "type": "Polygon",
        "coordinates": [[[20, 20], [21, 20], [21, 21], [20, 21], [20, 20]]],
    }
    with pytest.raises(
        GeoJSONOutsideCountryError,
        match="geojson is not inside the bounds of country NZL",
    ):
        await service.get_pop_shape("nzl", outside_geojson)


@pytest.mark.asyncio
async def test_fill_tile_cache_uses_each_iso3_once(monkeypatch):
    service = WorldPopService(db=object())
    seen = []

    async def fake_get_tile_path(iso3, skip_missing=False):
        seen.append((iso3, skip_missing))
        return f"/tmp/{iso3}.tif"

    service.get_tile_path = fake_get_tile_path  # type: ignore[method-assign]

    cached_paths = await service.fill_tile_cache("aus, NZL,aus,usa")

    assert seen == [("AUS", True), ("NZL", True), ("USA", True)]
    assert cached_paths == ["/tmp/AUS.tif", "/tmp/NZL.tif", "/tmp/USA.tif"]


@pytest.mark.asyncio
async def test_fill_tile_cache_skips_missing_tiles(monkeypatch):
    service = WorldPopService(db=object())
    seen = []

    async def fake_get_tile_path(iso3, skip_missing=False):
        seen.append((iso3, skip_missing))
        if iso3 == "NZL":
            raise TileNotFoundError(iso3)
        return f"/tmp/{iso3}.tif"

    service.get_tile_path = fake_get_tile_path  # type: ignore[method-assign]

    cached_paths = await service.fill_tile_cache("aus,nzl,usa")

    assert seen == [("AUS", True), ("NZL", True), ("USA", True)]
    assert cached_paths == ["/tmp/AUS.tif", "/tmp/USA.tif"]


@pytest.mark.asyncio
async def test_get_tile_path_propagates_missing_tile_error(monkeypatch):
    class _FakeScalarResult:
        def scalar_one_or_none(self):
            return None

    class _FakeDB:
        async def execute(self, *args, **kwargs):
            return _FakeScalarResult()

    service = WorldPopService(db=_FakeDB())

    async def fake_download(*args, **kwargs):
        raise TileNotFoundError("NZL")

    monkeypatch.setattr(service, "_download_and_cache_tile", fake_download)

    with pytest.raises(TileNotFoundError, match="no tile available for country NZL"):
        await service.get_tile_path("nzl")
