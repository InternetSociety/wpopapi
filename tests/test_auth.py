from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import SESSION_COOKIE_NAME
from app.database import get_db
from app.dependencies import pwd_context
from app.main import app


class _UnexpectedDB:
    async def execute(self, *_args, **_kwargs):
        raise AssertionError("An unrelated cookie must not trigger authentication")


class _FakeExecuteResult:
    def __init__(self, user):
        self.user = user

    def scalar_one_or_none(self):
        return self.user


class _FakeDB:
    def __init__(self, user):
        self.user = user

    async def execute(self, *_args, **_kwargs):
        return _FakeExecuteResult(self.user)


def test_unrelated_access_token_cookie_is_ignored():
    async def override_get_db():
        yield _UnexpectedDB()

    app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(app)
        client.cookies.set("access_token", "another-local-application-session")

        response = client.get("/")

        assert response.status_code == 200
        assert "Logged in as" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_web_login_and_logout_use_an_app_specific_session_cookie():
    user = SimpleNamespace(
        email="admin@example.com",
        password_hash=pwd_context.hash("correct-horse"),
        is_active=True,
    )

    async def override_get_db():
        yield _FakeDB(user)

    app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(app)
        client.cookies.set("access_token", "another-local-application-session")

        response = client.post(
            "/login",
            data={"username": "admin@example.com", "password": "correct-horse"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert SESSION_COOKIE_NAME == "wpopapi_session"
        assert SESSION_COOKIE_NAME in response.cookies
        assert client.cookies.get("access_token") == "another-local-application-session"

        logout = client.post("/logout", follow_redirects=False)

        assert logout.status_code == 302
        assert SESSION_COOKIE_NAME not in client.cookies
        assert client.cookies.get("access_token") == "another-local-application-session"
    finally:
        app.dependency_overrides.clear()
