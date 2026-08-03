from types import SimpleNamespace

import numpy as np
from fastapi.testclient import TestClient
import rasterio
from rasterio.transform import from_origin

from app.config import settings
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


def test_pop_radius_returns_422_when_center_is_outside_country(tmp_path, monkeypatch):
    raster_path = tmp_path / "AUS_pop.tif"
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

    try:
        client = TestClient(app)
        response = client.get(
            "/api/pop-radius",
            params={"iso3": "AUS", "lat": -80.0, "lon": 170.0, "radius": 10000},
        )
        assert response.status_code == 422
        assert response.json() == {
            "detail": "coordinates supplied are outside of the country specified"
        }
    finally:
        app.dependency_overrides.clear()


def test_pop_radius_uses_configured_limits(monkeypatch):
    async def override_get_db():
        yield object()

    def override_get_current_active_user():
        return SimpleNamespace(email="user@example.com", is_admin=False)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    monkeypatch.setattr(settings, "POP_RADIUS_MIN_METERS", 10.0)
    monkeypatch.setattr(settings, "POP_RADIUS_MAX_METERS", 20.0)

    try:
        client = TestClient(app)

        below_minimum = client.get(
            "/api/pop-radius",
            params={"iso3": "AUS", "lat": 0, "lon": 0, "radius": 9},
        )
        above_maximum = client.get(
            "/api/pop-radius",
            params={"iso3": "AUS", "lat": 0, "lon": 0, "radius": 21},
        )

        assert below_minimum.status_code == 422
        assert above_maximum.status_code == 422
        assert below_minimum.json() == above_maximum.json()
        assert below_minimum.json() == {
            "detail": "radius must be between 10 and 20 metres (0.02 km)."
        }
    finally:
        app.dependency_overrides.clear()
