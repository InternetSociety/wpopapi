from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


SESSION_COOKIE_NAME = "wpopapi_session"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    APP_NAME: str = "WorldPop Population API"
    DATABASE_URL: str
    TILE_CACHE_DIR: Path = Path("/app/data/tiles")
    TILE_CACHE_EXPIRY_DAYS: int = 365
    TILE_DOWNLOAD_TIMEOUT_SECONDS: float = 120.0

    POP_RADIUS_MIN_METERS: float = 1.0
    POP_RADIUS_MAX_METERS: float = 100_000.0
    GEOJSON_MAX_SIZE_BYTES: int = 5 * 1024 * 1024
    GEOJSON_MAX_VERTICES: int = 10_000

    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_MAX_LENGTH: int = 128

    SECRET_KEY: SecretStr
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    SESSION_EXPIRE_MINUTES: int = 60 * 24 * 7
    SESSION_COOKIE_SECURE: bool = False

    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 25
    SMTP_SENDER: str = "noreply@example.invalid"


settings = Settings()

dataset = "Global_2015_2030"
release = "R2025A"
version = "v1"
year = 2025
