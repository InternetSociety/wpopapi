from jose import jwt

from app.config import settings
from app.services.security import decode_jwt


def test_jwt_without_expiry_is_rejected() -> None:
    token = jwt.encode(
        {"sub": "user@example.com", "credential_type": "access"},
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )

    assert decode_jwt(token, "access") is None
