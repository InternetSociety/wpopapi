from collections.abc import AsyncIterator, Awaitable, Callable

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, get_db
from app.main import app
from app.models.models import User
from app.services.security import password_hasher


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)

        async def override_get_db() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_db] = override_get_db
        try:
            yield session
        finally:
            app.dependency_overrides.clear()
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def user_factory(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[User]]:
    async def create_user(
        email: str,
        *,
        is_admin: bool = False,
        is_active: bool = True,
        bearer_token: str | None = None,
        password: str = "correct-horse",
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hasher.hash(password),
            is_admin=is_admin,
            is_active=is_active,
            bearer_token=None if is_admin else (bearer_token or f"token-{email}"),
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return create_user
