from collections.abc import Awaitable, Callable
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.repositories.users import UserRepository
from app.services.exceptions import ProhibitedUserOperationError
from app.services.users import UserService


UserFactory = Callable[..., Awaitable[User]]


@pytest.mark.asyncio
async def test_service_protects_last_active_administrator(
    db_session: AsyncSession, user_factory: UserFactory
) -> None:
    target = await user_factory("only-admin@example.com", is_admin=True)
    actor = SimpleNamespace(id=999)
    service = UserService(UserRepository(db_session))

    with pytest.raises(ProhibitedUserOperationError):
        await service.toggle_active(target.id, actor)  # type: ignore[arg-type]
    with pytest.raises(ProhibitedUserOperationError):
        await service.toggle_admin(target.id, actor)  # type: ignore[arg-type]
    with pytest.raises(ProhibitedUserOperationError):
        await service.delete_user(target.id, actor)  # type: ignore[arg-type]
