import os
from functools import lru_cache

from pydantic import BaseModel, Field


class Settings(BaseModel):
    redis_url: str = Field(
        default_factory=lambda: os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )
    duckdb_path: str = Field(
        default_factory=lambda: os.environ.get("DUCKDB_PATH", "data/search_events.duckdb")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
