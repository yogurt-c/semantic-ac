from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

from ai_engine.db_reader import _as_utc, fetch_search_events


@pytest.fixture
def duckdb_path(tmp_path: Path) -> str:
    db_path = str(tmp_path / "events.duckdb")
    connection = duckdb.connect(db_path)
    connection.execute(
        "CREATE TABLE search_events "
        "(prefix VARCHAR, selected VARCHAR, action VARCHAR, event_ts TIMESTAMP, session_id VARCHAR)"
    )
    connection.execute(
        "INSERT INTO search_events VALUES (?, ?, ?, ?, ?)",
        ["노트북", "노트북 추천", "suggestion_click", datetime(2026, 7, 27, 10, 0, 0), "session-1"],
    )
    connection.execute(
        "INSERT INTO search_events VALUES (?, ?, ?, ?, ?)",
        ["키보드", "기계식 키보드", "final_search", datetime(2026, 7, 27, 11, 0, 0), "session-2"],
    )
    connection.close()
    return db_path


def test_fetch_search_events_reads_all_rows(duckdb_path: str):
    events = fetch_search_events(duckdb_path)

    assert len(events) == 2
    assert events[0].prefix == "노트북"
    assert events[0].selected == "노트북 추천"
    assert events[0].action == "suggestion_click"
    assert events[0].session_id == "session-1"


def test_fetch_search_events_normalizes_timestamps_to_utc(duckdb_path: str):
    events = fetch_search_events(duckdb_path)
    assert all(event.event_ts.tzinfo is not None for event in events)


def test_fetch_search_events_rejects_unsafe_table_name(duckdb_path: str):
    with pytest.raises(ValueError):
        fetch_search_events(duckdb_path, table="search_events; DROP TABLE search_events;--")


def test_fetch_search_events_returns_empty_list_for_empty_table(tmp_path: Path):
    db_path = str(tmp_path / "empty.duckdb")
    connection = duckdb.connect(db_path)
    connection.execute(
        "CREATE TABLE search_events "
        "(prefix VARCHAR, selected VARCHAR, action VARCHAR, event_ts TIMESTAMP, session_id VARCHAR)"
    )
    connection.close()

    assert fetch_search_events(db_path) == []


def test_as_utc_converts_already_aware_timestamp_to_utc():
    kst = timezone(timedelta(hours=9))
    aware = datetime(2026, 7, 27, 19, 0, 0, tzinfo=kst)

    converted = _as_utc(aware)

    assert converted.tzinfo == timezone.utc
    assert converted.hour == 10
