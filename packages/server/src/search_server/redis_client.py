from functools import lru_cache

import redis

from search_server.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)
