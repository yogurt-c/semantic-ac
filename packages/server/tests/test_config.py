import redis

from search_server.config import Settings, get_settings
from search_server.redis_client import get_redis_client


def test_settings_default_redis_url_and_duckdb_path(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)

    settings = Settings()

    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.duckdb_path == "data/search_events.duckdb"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_get_redis_client_builds_a_real_redis_client():
    get_redis_client.cache_clear()

    client = get_redis_client()

    assert isinstance(client, redis.Redis)
