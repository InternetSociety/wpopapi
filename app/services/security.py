import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.config import settings


CredentialType = Literal["session", "access"]


class PasswordHasher:
    def __init__(self) -> None:
        self._password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))

    def hash(self, password: str | bytes) -> str:
        return self._password_hash.hash(password)

    def verify(self, password: str | bytes, password_hash: str) -> bool:
        if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
            password_bytes = (
                password.encode("utf-8") if isinstance(password, str) else password
            )
            password = password_bytes[:72]
        return self._password_hash.verify(password, password_hash)


password_hasher = PasswordHasher()


def create_jwt(
    email: str,
    credential_type: CredentialType,
    expires_minutes: int,
) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    payload = {"sub": email, "exp": expires_at, "credential_type": credential_type}
    return jwt.encode(
        payload,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )


def decode_jwt(token: str, expected_type: CredentialType) -> str | None:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError:
        return None
    subject = payload.get("sub")
    if not isinstance(subject, str):
        return None
    if payload.get("credential_type") != expected_type:
        return None
    return subject.lower()


def csrf_token(session_token: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.get_secret_value().encode(),
        session_token.encode(),
        hashlib.sha256,
    ).hexdigest()


def csrf_token_is_valid(session_token: str, supplied_token: str) -> bool:
    return hmac.compare_digest(csrf_token(session_token), supplied_token)
