from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.dependencies import get_current_active_user, get_current_admin_user


class _FakeScalarResult:
    def all(self):
        return [
            SimpleNamespace(
                id=1,
                tile_id="AUS",
                file_path="/tmp/aus_pop.tif",
                last_used_at="2026-07-06 00:00:00",
                expires_at="2026-07-07 00:00:00",
            )
        ]


class _FakeExecuteResult:
    def scalars(self):
        return _FakeScalarResult()


class _FakeDB:
    async def execute(self, *args, **kwargs):
        return _FakeExecuteResult()


def test_tile_cache_page_allows_active_non_admin_user():
    async def override_get_db():
        yield _FakeDB()

    def override_get_current_active_user():
        return SimpleNamespace(email="user@example.com", is_admin=False)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user

    try:
        client = TestClient(app)
        response = client.get("/tile-cache")
        assert response.status_code == 200
        assert "Tile Cache" in response.text
        assert "user@example.com" in response.text
        assert "AUS" in response.text
    finally:
        app.dependency_overrides.clear()


def test_tile_cache_page_shows_admin_fill_form():
    async def override_get_db():
        yield _FakeDB()

    def override_get_current_active_user():
        return SimpleNamespace(email="admin@example.com", is_admin=True)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user

    try:
        client = TestClient(app)
        response = client.get("/tile-cache")
        assert response.status_code == 200
        assert "Fill tile cache" in response.text
        assert "Cache tiles" in response.text
    finally:
        app.dependency_overrides.clear()


def test_tile_cache_fill_redirects_for_admin(monkeypatch):
    async def override_get_db():
        yield _FakeDB()

    def override_get_current_admin_user():
        return SimpleNamespace(email="admin@example.com", is_admin=True)

    called = {}

    async def fake_process_tile_cache_fill(iso3_codes):
        called["iso3_codes"] = iso3_codes

    monkeypatch.setattr("app.routers.auth._process_tile_cache_fill", fake_process_tile_cache_fill)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin_user] = override_get_current_admin_user

    try:
        client = TestClient(app)
        response = client.post("/tile-cache/fill", data={"iso3_codes": "aus,nzl"}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/tile-cache?status=success")
        assert called["iso3_codes"] == "AUS,NZL"
    finally:
        app.dependency_overrides.clear()
