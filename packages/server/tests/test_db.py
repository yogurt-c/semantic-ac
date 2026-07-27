import threading
from datetime import UTC, datetime

import duckdb

from search_server.db import get_db_connection, insert_event


def test_get_db_connection_creates_file_and_table(tmp_path, monkeypatch):
    from search_server.config import get_settings
    from search_server.db import _connection

    get_settings.cache_clear()
    _connection.cache_clear()
    db_path = tmp_path / "nested" / "search_events.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))

    conn = get_db_connection()

    assert isinstance(conn, duckdb.DuckDBPyConnection)
    tables = conn.execute("SHOW TABLES").fetchall()
    assert ("search_events",) in tables

    conn.close()
    get_settings.cache_clear()
    _connection.cache_clear()

    assert db_path.exists()
    assert db_path.parent.is_dir()


def test_concurrent_inserts_via_get_db_connection_do_not_error(tmp_path, monkeypatch):
    from search_server.config import get_settings
    from search_server.db import _connection

    get_settings.cache_clear()
    _connection.cache_clear()
    db_path = tmp_path / "concurrent.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))

    thread_count = 20
    errors: list[Exception] = []
    errors_lock = threading.Lock()

    def worker(i: int) -> None:
        try:
            conn = get_db_connection()
            insert_event(
                conn,
                f"prefix-{i}",
                f"selected-{i}",
                "final_search",
                datetime.now(UTC).replace(tzinfo=None),
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

    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM search_events").fetchone()[0]
    assert count == thread_count

    conn.close()
    get_settings.cache_clear()
    _connection.cache_clear()
