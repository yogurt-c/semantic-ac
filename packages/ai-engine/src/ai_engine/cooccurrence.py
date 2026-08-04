from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations

from ai_engine.events import SearchEvent

DEFAULT_HALF_LIFE_HOURS = 24.0 * 7
DEFAULT_TOP_N_PER_TERM = 10
DEFAULT_SEED_SIZE = 3
DEFAULT_MIN_OCCURRENCES = 1

CooccurrenceScores = dict[str, list[tuple[str, float]]]


def build_cooccurrence_scores(
    events: list[SearchEvent],
    *,
    now: datetime | None = None,
    half_life_hours: float = DEFAULT_HALF_LIFE_HOURS,
    top_n_per_term: int = DEFAULT_TOP_N_PER_TERM,
    min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
) -> CooccurrenceScores:
    """세션 내에서 함께 selected된 키워드 쌍을 최신성 감쇠 가중치로 누적한다.

    prefix 기반 score_keywords는 "같은 prefix"끼리만 묶어 문자열이 겹치는 완성어
    랭킹만 만들 수 있다. 반면 이 함수는 session_id로 묶인 실제 검색 행동 시퀀스에서
    서로 다른 완성어가 같은 세션에 함께 등장한 빈도를 학습하므로, "노트북"과 "맥북"처럼
    문자열은 전혀 겹치지 않지만 실제 사용자들이 연달아 찾는 진짜 연관 키워드를
    시간이 지날수록(더 많은 세션이 쌓일수록) 자연히 강화한다.

    half_life는 score_keywords의 기본값(24h)보다 길게 잡는다(기본 1주) — 같은 prefix
    재검색보다 세션 co-occurrence는 표본이 희소한 신호라서 너무 빨리 감쇠하면
    데이터가 쌓이기 전에 사라진다.

    min_occurrences로 두 키워드가 함께 selected된 세션 수(raw count)가 기준
    미달인 쌍을 걸러낸다 — 우연히 한 세션에서만 같이 나온 무관한 쌍이 연관
    검색어로 노출되는 것을 막는다. 기본값 1은 필터링 없음(하위 호환)과 동일하다.
    """
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    if top_n_per_term <= 0:
        raise ValueError("top_n_per_term must be positive")
    if min_occurrences <= 0:
        raise ValueError("min_occurrences must be positive")

    reference_time = now if now is not None else datetime.now(timezone.utc)

    sessions: dict[str, list[SearchEvent]] = {}
    for event in events:
        if not event.session_id:
            continue
        sessions.setdefault(event.session_id, []).append(event)

    pair_scores: dict[tuple[str, str], float] = {}
    pair_counts: dict[tuple[str, str], int] = {}
    for session_events in sessions.values():
        distinct_terms = sorted({event.selected for event in session_events})
        if len(distinct_terms) < 2:
            continue

        session_last_ts = max(event.event_ts for event in session_events)
        age_hours = max(_hours_between(reference_time, session_last_ts), 0.0)
        decay = 0.5 ** (age_hours / half_life_hours)

        for term_a, term_b in combinations(distinct_terms, 2):
            pair_scores[(term_a, term_b)] = pair_scores.get((term_a, term_b), 0.0) + decay
            pair_counts[(term_a, term_b)] = pair_counts.get((term_a, term_b), 0) + 1

    scores_by_term: dict[str, dict[str, float]] = {}
    for (term_a, term_b), score in pair_scores.items():
        if pair_counts[(term_a, term_b)] < min_occurrences:
            continue
        scores_by_term.setdefault(term_a, {})[term_b] = score
        scores_by_term.setdefault(term_b, {})[term_a] = score

    return {
        term: sorted(related.items(), key=lambda pair: pair[1], reverse=True)[:top_n_per_term]
        for term, related in scores_by_term.items()
    }


def related_terms(
    scores_by_term: CooccurrenceScores,
    seed_terms: list[str],
    *,
    top_k: int = DEFAULT_TOP_N_PER_TERM,
) -> list[str]:
    """seed_terms(주로 prefix의 상위 완성어 후보들)와 co-occurrence로 연관된 키워드를
    점수 합산해 랭킹한다. seed_terms 자기 자신은 결과에서 제외한다."""
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    seed_set = set(seed_terms)
    aggregated: dict[str, float] = {}
    for seed in seed_terms:
        for related_term, score in scores_by_term.get(seed, []):
            if related_term in seed_set:
                continue
            aggregated[related_term] = aggregated.get(related_term, 0.0) + score

    ranked = sorted(aggregated.items(), key=lambda pair: pair[1], reverse=True)
    return [term for term, _ in ranked[:top_k]]


def _hours_between(reference_time: datetime, event_ts: datetime) -> float:
    return (reference_time - event_ts).total_seconds() / 3600.0
