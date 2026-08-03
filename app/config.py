import os
from pydantic_settings import BaseSettings

SESSION_COOKIE_NAME = "wpopapi_session"


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///app/data/app.db"
    SQL_SETUP_FILE: str = "data_table_setup.sql"
    TILE_CACHE_DIR: str = "/app/data/tiles"
    TILE_CACHE_EXPIRY_DAYS: int = 365
    TILE_DOWNLOAD_TIMEOUT_SECONDS: float = 120.0

    POP_RADIUS_MIN_METERS: float = 1.0
    POP_RADIUS_MAX_METERS: float = 100_000.0
    GEOJSON_MAX_SIZE_BYTES: int = 5 * 1024 * 1024
    GEOJSON_MAX_VERTICES: int = 10_000

    SECRET_KEY: str = "super-secret-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week

    class Config:
        env_file = ".env"

settings = Settings()

dataset = "Global_2015_2030"
release = "R2025A"
version = "v1"
year = 2025

# Create cache dir if it doesn't exist locally for development
try:
    os.makedirs(settings.TILE_CACHE_DIR, exist_ok=True)
except OSError:
    # This might fail on read-only file systems during build or in some restricted envs
    pass
