import hashlib
import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.models import User
from app.repositories.users import UserRepository
from app.services.exceptions import (
    EmailAlreadyExistsError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidResetCodeError,
    InvalidUserDataError,
    ProhibitedUserOperationError,
    UserNotFoundError,
)
from app.services.security import create_jwt, decode_jwt, password_hasher
from app.services.email import PasswordResetMailer


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    @staticmethod
    def normalize_email(email: str) -> str:
        try:
            validated = TypeAdapter(EmailStr).validate_python(email.strip())
        except ValidationError as exc:
            raise InvalidUserDataError("A valid email address is required") from exc
        return str(validated).lower()

    async def authenticate_password(self, email: str, password: str) -> User:
        user = await self.repository.get_by_email(self.normalize_email(email))
        if user is None or not password_hasher.verify(password, user.password_hash):
            raise InvalidCredentialsError("Incorrect email or password")
        if not user.is_active:
            raise InactiveUserError("Incorrect email or password")
        user.last_login_at = datetime.now(UTC)
        await self.repository.flush()
        return user

    def create_session_jwt(self, user: User) -> str:
        return create_jwt(user.email, "session", settings.SESSION_EXPIRE_MINUTES)

    def create_access_jwt(self, user: User) -> str:
        return create_jwt(user.email, "access", settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    async def resolve_bearer(self, token: str) -> User | None:
        user = await self.repository.get_by_bearer_token(token)
        if user is not None:
            return user
        email = decode_jwt(token, "access")
        return await self.repository.get_by_email(email) if email else None

    async def resolve_session(self, token: str) -> User | None:
        email = decode_jwt(token, "session")
        return await self.repository.get_by_email(email) if email else None

    async def visible_users(self, current_user: User) -> list[User]:
        if current_user.is_admin:
            return await self.repository.list_all()
        return [current_user]

    async def create_user(self, email: str, password: str, is_admin: bool) -> User:
        self.validate_password(password)
        normalized_email = self.normalize_email(email)
        if await self.repository.get_by_email(normalized_email):
            raise EmailAlreadyExistsError("A user with that email already exists")
        user = User(
            email=normalized_email,
            password_hash=password_hasher.hash(password),
            bearer_token=None if is_admin else secrets.token_urlsafe(32),
            is_active=True,
            is_admin=is_admin,
        )
        self.repository.add(user)
        try:
            await self.repository.flush()
        except IntegrityError as exc:
            raise EmailAlreadyExistsError(
                "A user with that email already exists"
            ) from exc
        return user

    @staticmethod
    def validate_password(password: str) -> None:
        minimum = settings.PASSWORD_MIN_LENGTH
        maximum = settings.PASSWORD_MAX_LENGTH
        if not minimum <= len(password) <= maximum:
            raise InvalidUserDataError(
                f"Password length must be between {minimum} and {maximum} characters"
            )

    async def request_password_reset(
        self, email: str, mailer: PasswordResetMailer
    ) -> None:
        user = await self.repository.get_by_email(self.normalize_email(email))
        if user is None or not user.is_active:
            return

        code = secrets.token_urlsafe(48)
        user.reset_token_hash = hashlib.sha256(code.encode()).hexdigest()
        user.reset_token_expires_at = datetime.now(UTC) + timedelta(minutes=30)
        await self.repository.flush()
        try:
            await mailer.send(user.email, code)
        except OSError, smtplib.SMTPException:
            user.reset_token_hash = None
            user.reset_token_expires_at = None
            await self.repository.flush()
            logging.exception("Password-reset email delivery failed")

    async def reset_password(self, code: str, password: str) -> None:
        token_hash = hashlib.sha256(code.encode()).hexdigest()
        user = await self.repository.get_by_reset_token_hash(token_hash)
        now = datetime.now(UTC)
        if (
            user is None
            or not user.is_active
            or user.reset_token_expires_at is None
            or _as_utc(user.reset_token_expires_at) < now
        ):
            raise InvalidResetCodeError("The reset code is invalid or has expired")
        self.validate_password(password)
        user.password_hash = password_hasher.hash(password)
        user.reset_token_hash = None
        user.reset_token_expires_at = None
        await self.repository.flush()

    async def create_initial_admin(self, email: str, password: str) -> User:
        return await self.create_user(email, password, is_admin=True)

    async def regenerate_token(self, user_id: int) -> User:
        user = await self._get_user(user_id)
        if user.is_admin:
            raise ProhibitedUserOperationError(
                "Administrators cannot have persistent tokens"
            )
        user.bearer_token = secrets.token_urlsafe(32)
        await self.repository.flush()
        return user

    async def toggle_active(self, user_id: int, actor: User) -> User:
        user = await self._get_user(user_id)
        if user.id == actor.id:
            raise ProhibitedUserOperationError("You cannot deactivate your own account")
        if user.is_active and user.is_admin:
            await self._protect_last_active_admin()
        user.is_active = not user.is_active
        await self.repository.flush()
        return user

    async def toggle_admin(self, user_id: int, actor: User) -> User:
        user = await self._get_user(user_id)
        if user.id == actor.id:
            raise ProhibitedUserOperationError("You cannot change your own role")
        if user.is_admin:
            if user.is_active:
                await self._protect_last_active_admin()
            user.is_admin = False
            user.bearer_token = secrets.token_urlsafe(32)
        else:
            user.is_admin = True
            user.bearer_token = None
        await self.repository.flush()
        return user

    async def delete_user(self, user_id: int, actor: User) -> None:
        user = await self._get_user(user_id)
        if user.id == actor.id:
            raise ProhibitedUserOperationError("You cannot delete your own account")
        if user.is_admin and user.is_active:
            await self._protect_last_active_admin()
        await self.repository.delete(user)
        await self.repository.flush()

    async def remove_user_by_email(self, email: str) -> None:
        user = await self.repository.get_by_email(self.normalize_email(email))
        if user is None:
            raise UserNotFoundError("User not found")
        if user.is_admin and user.is_active:
            await self._protect_last_active_admin()
        await self.repository.delete(user)
        await self.repository.flush()

    async def _get_user(self, user_id: int) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found")
        return user

    async def _protect_last_active_admin(self) -> None:
        if await self.repository.count_active_admins() <= 1:
            raise ProhibitedUserOperationError(
                "The last active administrator must remain active"
            )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
