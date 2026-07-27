import os
from functools import lru_cache

from pydantic import BaseModel, Field


def _parse_allowed_origins(raw: str) -> list[str]:
    origins = [origin.strip() for origin in raw.split(",")]
    return [origin for origin in origins if origin]


class Settings(BaseModel):
    redis_url: str = Field(
        default_factory=lambda: os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )
    duckdb_path: str = Field(
        default_factory=lambda: os.environ.get("DUCKDB_PATH", "data/search_events.duckdb")
    )
    allowed_origins: list[str] = Field(
        default_factory=lambda: _parse_allowed_origins(os.environ.get("ALLOWED_ORIGINS", "*"))
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
