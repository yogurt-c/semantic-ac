from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ai_engine.events import SearchEvent

DEFAULT_HALF_LIFE_HOURS = 24.0
DEFAULT_TOP_N = 20


@dataclass(frozen=True, slots=True)
class ScoredKeyword:
    keyword: str
    score: float


def score_keywords(
    events: list[SearchEvent],
    *,
    now: datetime | None = None,
    half_life_hours: float = DEFAULT_HALF_LIFE_HOURS,
    top_n: int = DEFAULT_TOP_N,
) -> list[ScoredKeyword]:
    """이벤트의 `selected` 값을 빈도 + 최신성(지수 감쇠) 합산 점수로 랭킹한다.

    score(keyword) = sum(0.5 ** (age_hours / half_life_hours)) - 이벤트를 순수 입력으로만
    받으므로 DB 접근 없이 유닛테스트가 가능하다.
    """
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    reference_time = now if now is not None else datetime.now(timezone.utc)

    scores: dict[str, float] = {}
    for event in events:
        age_hours = max(_hours_between(reference_time, event.event_ts), 0.0)
        decay = 0.5 ** (age_hours / half_life_hours)
        scores[event.selected] = scores.get(event.selected, 0.0) + decay

    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    return [ScoredKeyword(keyword=keyword, score=score) for keyword, score in ranked[:top_n]]


def group_events_by_prefix(events: list[SearchEvent]) -> dict[str, list[SearchEvent]]:
    """prefix별로 이벤트를 묶는다 (배치 파이프라인이 prefix 단위로 순회하기 위한 전처리)."""
    grouped: dict[str, list[SearchEvent]] = {}
    for event in events:
        grouped.setdefault(event.prefix, []).append(event)
    return grouped


def _hours_between(reference_time: datetime, event_ts: datetime) -> float:
    return (reference_time - event_ts).total_seconds() / 3600.0
