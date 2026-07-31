from io import BytesIO
from types import SimpleNamespace

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.database import get_db
from app.dependencies import get_current_active_user
from app.main import app
from app.services.worldpop import WorldPopService


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


def test_pop_shape_accepts_geojson_file_upload(tmp_path, monkeypatch):
    raster_path = tmp_path / "NZL_pop.tif"
    _write_test_raster(raster_path)

    async def override_get_db():
        yield object()

    def override_get_current_active_user():
        return SimpleNamespace(email="user@example.com", is_admin=False)

    async def fake_get_tile_path(self, _iso3):
        return str(raster_path)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    monkeypatch.setattr(WorldPopService, "get_tile_path", fake_get_tile_path)

    geojson = (
        b'{"type":"Polygon","coordinates":[[[0,10],[2,10],[2,8],[0,8],[0,10]]]}'
    )

    try:
        client = TestClient(app)
        response = client.post(
            "/api/pop-shape",
            params={"iso3": "nzl"},
            files={"geojson_file": ("shape.geojson", BytesIO(geojson), "application/geo+json")},
        )
        assert response.status_code == 200
        assert response.json() == {"pop": 26}
    finally:
        app.dependency_overrides.clear()


def test_pop_shape_returns_422_when_geojson_is_outside_tile(tmp_path, monkeypatch):
    raster_path = tmp_path / "NZL_pop.tif"
    _write_test_raster(raster_path)

    async def override_get_db():
        yield object()

    def override_get_current_active_user():
        return SimpleNamespace(email="user@example.com", is_admin=False)

    async def fake_get_tile_path(self, _iso3):
        return str(raster_path)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    monkeypatch.setattr(WorldPopService, "get_tile_path", fake_get_tile_path)

    geojson = (
        b'{"type":"Polygon","coordinates":[[[20,20],[21,20],[21,21],[20,21],[20,20]]]}'
    )

    try:
        client = TestClient(app)
        response = client.post(
            "/api/pop-shape",
            params={"iso3": "nzl"},
            files={"geojson_file": ("shape.geojson", BytesIO(geojson), "application/geo+json")},
        )
        assert response.status_code == 422
        assert response.json() == {
            "detail": "geojson is not inside the bounds of country NZL"
        }
    finally:
        app.dependency_overrides.clear()
