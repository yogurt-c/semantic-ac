from __future__ import annotations

from datetime import timedelta

import pytest

from ai_engine.events import SearchEvent
from ai_engine.scoring import group_events_by_prefix, score_keywords


def test_returns_empty_list_when_no_events(reference_time):
    assert score_keywords([], now=reference_time) == []


def test_ranks_by_frequency_when_recency_effect_is_small(sample_events, reference_time):
    scored = score_keywords(sample_events, now=reference_time, half_life_hours=24.0)
    keywords = [item.keyword for item in scored]
    assert keywords[0] == "노트북 추천"


def test_recent_event_outscores_older_higher_frequency(reference_time):
    events = [
        SearchEvent(
            prefix="a",
            selected="old_frequent",
            action="final_search",
            event_ts=reference_time - timedelta(hours=1000),
        ),
        SearchEvent(
            prefix="a",
            selected="old_frequent",
            action="final_search",
            event_ts=reference_time - timedelta(hours=1000),
        ),
        SearchEvent(
            prefix="a",
            selected="recent_rare",
            action="final_search",
            event_ts=reference_time - timedelta(minutes=1),
        ),
    ]
    scored = score_keywords(events, now=reference_time, half_life_hours=1.0)
    assert scored[0].keyword == "recent_rare"


def test_respects_top_n_limit(sample_events, reference_time):
    scored = score_keywords(sample_events, now=reference_time, top_n=1)
    assert len(scored) == 1


def test_rejects_non_positive_half_life(sample_events, reference_time):
    with pytest.raises(ValueError):
        score_keywords(sample_events, now=reference_time, half_life_hours=0)


@pytest.mark.parametrize("invalid_top_n", [0, -1, -10])
def test_rejects_non_positive_top_n(sample_events, reference_time, invalid_top_n):
    with pytest.raises(ValueError):
        score_keywords(sample_events, now=reference_time, top_n=invalid_top_n)


def test_defaults_now_to_current_time_when_omitted(sample_events):
    scored = score_keywords(sample_events)
    assert len(scored) > 0


def test_min_occurrences_filters_out_keywords_below_threshold(sample_events, reference_time):
    """"가성비 노트북"과 "기계식 키보드"는 각각 1회만 등장한다."""
    scored = score_keywords(sample_events, now=reference_time, min_occurrences=2)
    keywords = [item.keyword for item in scored]

    assert "노트북 추천" in keywords  # 2회 등장
    assert "가성비 노트북" not in keywords
    assert "기계식 키보드" not in keywords


def test_min_occurrences_default_does_not_filter_single_occurrences(sample_events, reference_time):
    scored = score_keywords(sample_events, now=reference_time)
    keywords = [item.keyword for item in scored]

    assert "가성비 노트북" in keywords


def test_rejects_non_positive_min_occurrences(sample_events, reference_time):
    with pytest.raises(ValueError):
        score_keywords(sample_events, now=reference_time, min_occurrences=0)


def test_group_events_by_prefix(sample_events):
    grouped = group_events_by_prefix(sample_events)
    assert set(grouped.keys()) == {"노트북", "키보드"}
    assert len(grouped["노트북"]) == 3
    assert len(grouped["키보드"]) == 1


def test_group_events_by_prefix_empty_input():
    assert group_events_by_prefix([]) == {}
