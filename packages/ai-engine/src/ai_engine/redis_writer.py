from __future__ import annotations

import json

import redis

SUGGESTION_KEY_PREFIX = "sugg:"


def suggestion_key(prefix: str) -> str:
    """docs/CONTRACT.md 섹션 3: `sugg:{prefix}` 키 포맷."""
    return f"{SUGGESTION_KEY_PREFIX}{prefix}"


def write_suggestions(client: redis.Redis, prefix: str, suggestions: list[str]) -> None:
    """sugg:{prefix} 키에 JSON 배열 문자열을 SET한다.

    단일 키 SET은 Redis에서 원자적이므로 별도 트랜잭션/스테이징 키 없이도
    읽는 쪽(트랙 B)은 항상 이전 값 전체 또는 새 값 전체만 관측한다.
    """
    payload = json.dumps(suggestions, ensure_ascii=False)
    client.set(suggestion_key(prefix), payload)
