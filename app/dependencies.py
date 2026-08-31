from typing import Annotated

from fastapi import Depends, Form, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SESSION_COOKIE_NAME
from app.database import get_db
from app.models.models import User
from app.repositories.tiles import TileRepository
from app.repositories.users import UserRepository
from app.services.security import csrf_token_is_valid, password_hasher
from app.services.users import UserService
from app.services.worldpop import WorldPopService


# Kept as a stable adapter name for callers that need password hashing.
pwd_context = password_hasher


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db))


def get_worldpop_service(db: AsyncSession = Depends(get_db)) -> WorldPopService:
    return WorldPopService(db)


def get_tile_repository(db: AsyncSession = Depends(get_db)) -> TileRepository:
    return TileRepository(db)


async def get_current_user(
    request: Request,
    service: UserService = Depends(get_user_service),
) -> User | None:
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, separator, token = authorization.partition(" ")
        if separator and scheme.lower() == "bearer" and token:
            return await service.resolve_bearer(token)
        return None

    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return None
    return await service.resolve_session(session_token)


async def get_current_active_user(
    request: Request,
    current_user: User | None = Depends(get_current_user),
) -> User:
    if current_user is None:
        if request.url.path.startswith("/api") or request.url.path == "/openapi.json":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/"},
        )
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user


async def verify_csrf(
    request: Request,
    supplied_token: Annotated[str | None, Form(alias="csrf_token")] = None,
) -> None:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if (
        not session_token
        or not supplied_token
        or not csrf_token_is_valid(session_token, supplied_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )
