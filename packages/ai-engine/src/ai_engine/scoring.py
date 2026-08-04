from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ai_engine.events import SearchEvent

DEFAULT_HALF_LIFE_HOURS = 24.0
DEFAULT_TOP_N = 20
DEFAULT_MIN_OCCURRENCES = 1


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
    min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
) -> list[ScoredKeyword]:
    """이벤트의 `selected` 값을 빈도 + 최신성(지수 감쇠) 합산 점수로 랭킹한다.

    score(keyword) = sum(0.5 ** (age_hours / half_life_hours)) - 이벤트를 순수 입력으로만
    받으므로 DB 접근 없이 유닛테스트가 가능하다.

    min_occurrences로 실제 등장 횟수(감쇠 미적용 raw count)가 기준 미달인 키워드를
    걸러낸다 — 오타/노이즈성 selected 값이 1회 등장만으로 추천 후보가 되는 것을 막는다.
    기본값 1은 필터링 없음(하위 호환)과 동일하다.
    """
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    if min_occurrences <= 0:
        raise ValueError("min_occurrences must be positive")

    reference_time = now if now is not None else datetime.now(timezone.utc)

    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    for event in events:
        age_hours = max(_hours_between(reference_time, event.event_ts), 0.0)
        decay = 0.5 ** (age_hours / half_life_hours)
        scores[event.selected] = scores.get(event.selected, 0.0) + decay
        counts[event.selected] = counts.get(event.selected, 0) + 1

    eligible = ((keyword, score) for keyword, score in scores.items() if counts[keyword] >= min_occurrences)
    ranked = sorted(eligible, key=lambda pair: pair[1], reverse=True)
    return [ScoredKeyword(keyword=keyword, score=score) for keyword, score in ranked[:top_n]]


def group_events_by_prefix(events: list[SearchEvent]) -> dict[str, list[SearchEvent]]:
    """prefix별로 이벤트를 묶는다 (배치 파이프라인이 prefix 단위로 순회하기 위한 전처리)."""
    grouped: dict[str, list[SearchEvent]] = {}
    for event in events:
        grouped.setdefault(event.prefix, []).append(event)
    return grouped


def _hours_between(reference_time: datetime, event_ts: datetime) -> float:
    return (reference_time - event_ts).total_seconds() / 3600.0
