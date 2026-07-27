import threading
from contextlib import contextmanager
from datetime import UTC, datetime

import duckdb

from search_server.config import get_settings
from search_server.db import get_db_connection, insert_event


def test_get_db_connection_creates_file_and_table(tmp_path, monkeypatch):
    get_settings.cache_clear()
    db_path = tmp_path / "nested" / "search_events.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))

    with contextmanager(get_db_connection)() as conn:
        assert isinstance(conn, duckdb.DuckDBPyConnection)
        tables = conn.execute("SHOW TABLES").fetchall()
        assert ("search_events",) in tables

    get_settings.cache_clear()
    assert db_path.exists()
    assert db_path.parent.is_dir()


def test_db_connection_closes_after_dependency_teardown(tmp_path, monkeypatch):
    """DuckDB는 연결이 열려 있는 동안 파일 락을 유지하므로, 요청 처리 후 연결을
    닫아야 같은 파일을 read_only로 여는 별도 프로세스(AI 배치 워커)가 차단되지
    않는다 (docs/CONTRACT.md 섹션 2)."""
    get_settings.cache_clear()
    db_path = tmp_path / "search_events.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))

    with contextmanager(get_db_connection)() as conn:
        insert_event(
            conn,
            "노트북",
            "노트북 추천",
            "final_search",
            datetime.now(UTC).replace(tzinfo=None),
            "session-1",
        )

    reader = duckdb.connect(str(db_path), read_only=True)
    try:
        count = reader.execute("SELECT COUNT(*) FROM search_events").fetchone()[0]
        assert count == 1
    finally:
        reader.close()

    get_settings.cache_clear()


def test_concurrent_inserts_via_get_db_connection_do_not_error(tmp_path, monkeypatch):
    get_settings.cache_clear()
    db_path = tmp_path / "concurrent.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))

    thread_count = 20
    errors: list[Exception] = []
    errors_lock = threading.Lock()

    def worker(i: int) -> None:
        try:
            with contextmanager(get_db_connection)() as conn:
                insert_event(
                    conn,
                    f"prefix-{i}",
                    f"selected-{i}",
                    "final_search",
                    datetime.now(UTC).replace(tzinfo=None),
                    f"session-{i}",
                )
        except Exception as exc:  # noqa: BLE001
            with errors_lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        count = conn.execute("SELECT COUNT(*) FROM search_events").fetchone()[0]
        assert count == thread_count
    finally:
        conn.close()

    get_settings.cache_clear()
