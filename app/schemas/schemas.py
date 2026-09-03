from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import settings


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=settings.PASSWORD_MIN_LENGTH,
        max_length=settings.PASSWORD_MAX_LENGTH,
    )
    is_admin: bool = False


class UserUpdate(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


class UserPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None


class UserCredentialResponse(UserPublicResponse):
    bearer_token: str | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PopulationResponse(BaseModel):
    pop: int
