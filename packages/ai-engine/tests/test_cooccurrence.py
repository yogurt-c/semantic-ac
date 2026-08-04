from __future__ import annotations

from datetime import timedelta

import pytest

from ai_engine.cooccurrence import build_cooccurrence_scores, related_terms
from ai_engine.events import SearchEvent


def _event(prefix, selected, session_id, event_ts, action="final_search") -> SearchEvent:
    return SearchEvent(
        prefix=prefix, selected=selected, action=action, event_ts=event_ts, session_id=session_id
    )


def test_returns_empty_dict_for_no_events(reference_time):
    assert build_cooccurrence_scores([], now=reference_time) == {}


def test_ignores_events_without_session_id(reference_time):
    events = [
        _event("노트북", "노트북", None, reference_time),
        _event("맥북", "맥북", None, reference_time),
    ]

    assert build_cooccurrence_scores(events, now=reference_time) == {}


def test_ignores_sessions_with_a_single_distinct_term(reference_time):
    events = [
        _event("노트북", "노트북", "s1", reference_time - timedelta(minutes=1)),
        _event("노트북", "노트북", "s1", reference_time),
    ]

    assert build_cooccurrence_scores(events, now=reference_time) == {}


def test_links_two_terms_selected_in_the_same_session_symmetrically(reference_time):
    events = [
        _event("노트북", "노트북", "s1", reference_time - timedelta(minutes=5)),
        _event("맥북", "맥북", "s1", reference_time),
    ]

    scores = build_cooccurrence_scores(events, now=reference_time)

    assert [term for term, _ in scores["노트북"]] == ["맥북"]
    assert [term for term, _ in scores["맥북"]] == ["노트북"]


def test_recent_session_outscores_older_session(reference_time):
    events = [
        _event("노트북", "노트북", "old", reference_time - timedelta(hours=1000)),
        _event("노트북", "노트북", "old", reference_time - timedelta(hours=1000)),
        _event("그램", "그램", "old", reference_time - timedelta(hours=1000)),
        _event("노트북", "노트북", "recent", reference_time - timedelta(minutes=1)),
        _event("맥북", "맥북", "recent", reference_time - timedelta(minutes=1)),
    ]

    scores = build_cooccurrence_scores(events, now=reference_time, half_life_hours=1.0)

    related = [term for term, _ in scores["노트북"]]
    assert related[0] == "맥북"


def test_respects_top_n_per_term_limit(reference_time):
    events = [
        _event("노트북", "노트북", "s1", reference_time),
        _event("맥북", "맥북", "s1", reference_time),
        _event("그램", "그램", "s1", reference_time),
        _event("아이패드", "아이패드", "s1", reference_time),
    ]

    scores = build_cooccurrence_scores(events, now=reference_time, top_n_per_term=2)

    assert len(scores["노트북"]) == 2


def test_rejects_non_positive_half_life(reference_time):
    with pytest.raises(ValueError):
        build_cooccurrence_scores([], now=reference_time, half_life_hours=0)


def test_rejects_non_positive_top_n_per_term(reference_time):
    with pytest.raises(ValueError):
        build_cooccurrence_scores([], now=reference_time, top_n_per_term=0)


def test_rejects_non_positive_min_occurrences(reference_time):
    with pytest.raises(ValueError):
        build_cooccurrence_scores([], now=reference_time, min_occurrences=0)


def test_min_occurrences_filters_out_pairs_seen_in_only_one_session(reference_time):
    events = [
        _event("노트북", "노트북", "s1", reference_time),
        _event("맥북", "맥북", "s1", reference_time),
    ]

    scores = build_cooccurrence_scores(events, now=reference_time, min_occurrences=2)

    assert scores == {}


def test_min_occurrences_keeps_pairs_seen_in_enough_sessions(reference_time):
    events = [
        _event("노트북", "노트북", "s1", reference_time),
        _event("맥북", "맥북", "s1", reference_time),
        _event("노트북", "노트북", "s2", reference_time),
        _event("맥북", "맥북", "s2", reference_time),
    ]

    scores = build_cooccurrence_scores(events, now=reference_time, min_occurrences=2)

    assert [term for term, _ in scores["노트북"]] == ["맥북"]


def test_related_terms_aggregates_scores_across_seed_terms(reference_time):
    events = [
        _event("노트북", "노트북", "s1", reference_time),
        _event("맥북", "맥북", "s1", reference_time),
        _event("가성비 노트북", "가성비 노트북", "s2", reference_time),
        _event("맥북", "맥북", "s2", reference_time),
    ]
    scores = build_cooccurrence_scores(events, now=reference_time)

    result = related_terms(scores, ["노트북", "가성비 노트북"], top_k=5)

    assert result == ["맥북"]


def test_related_terms_excludes_seed_terms_from_results(reference_time):
    events = [
        _event("노트북", "노트북", "s1", reference_time),
        _event("맥북", "맥북", "s1", reference_time),
    ]
    scores = build_cooccurrence_scores(events, now=reference_time)

    result = related_terms(scores, ["노트북", "맥북"], top_k=5)

    assert result == []


def test_related_terms_respects_top_k(reference_time):
    events = [
        _event("노트북", "노트북", "s1", reference_time),
        _event("맥북", "맥북", "s1", reference_time),
        _event("그램", "그램", "s1", reference_time),
    ]
    scores = build_cooccurrence_scores(events, now=reference_time)

    result = related_terms(scores, ["노트북"], top_k=1)

    assert len(result) == 1


def test_related_terms_rejects_non_positive_top_k(reference_time):
    with pytest.raises(ValueError):
        related_terms({}, ["노트북"], top_k=0)


def test_related_terms_returns_empty_list_for_unknown_seed_terms(reference_time):
    assert related_terms({}, ["노트북"], top_k=5) == []
