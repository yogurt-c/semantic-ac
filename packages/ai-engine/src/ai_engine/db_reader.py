from __future__ import annotations

import re
from datetime import datetime, timezone

import duckdb

from ai_engine.events import SearchEvent

_VALID_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DEFAULT_TABLE = "search_events"


def fetch_search_events(db_path: str, *, table: str = DEFAULT_TABLE) -> list[SearchEvent]:
    """트랙 B가 적재하는 DuckDB search_events 테이블(docs/CONTRACT.md 섹션 2)에서 전체
    이벤트를 읽어온다. 배치 엔진과 실시간 서버 DB는 완전히 분리된 파일이므로 읽기 전용으로 연다.
    """
    if not _VALID_TABLE_NAME.match(table):
        raise ValueError(f"invalid table name: {table!r}")

    connection = duckdb.connect(db_path, read_only=True)
    try:
        rows = connection.execute(
            f"SELECT prefix, selected, action, event_ts FROM {table}"  # noqa: S608 - table validated above
        ).fetchall()
    finally:
        connection.close()

    return [
        SearchEvent(
            prefix=prefix,
            selected=selected,
            action=action,
            event_ts=_as_utc(event_ts),
        )
        for prefix, selected, action, event_ts in rows
    ]


def _as_utc(event_ts: datetime) -> datetime:
    if event_ts.tzinfo is None:
        return event_ts.replace(tzinfo=timezone.utc)
    return event_ts.astimezone(timezone.utc)
