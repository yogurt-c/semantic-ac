import os
import threading
from datetime import datetime

import duckdb

from search_server.config import get_settings

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS search_events (
    prefix VARCHAR,
    selected VARCHAR,
    action VARCHAR,
    event_ts TIMESTAMP
)
"""

# DuckDB connections are not safe for unsynchronized concurrent use across
# threads. FastAPI runs sync path operations in a threadpool, so both
# connection creation and every write must be serialized explicitly —
# functools.lru_cache alone does not prevent two threads from racing into
# duckdb.connect() on the same path (it only locks around cache bookkeeping,
# not the wrapped call itself).
_connections: dict[str, duckdb.DuckDBPyConnection] = {}
_connections_lock = threading.Lock()
_write_lock = threading.Lock()


def init_table(conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    conn.execute(CREATE_TABLE_SQL)
    return conn


def _connection(db_path: str) -> duckdb.DuckDBPyConnection:
    with _connections_lock:
        conn = _connections.get(db_path)
        if conn is None:
            directory = os.path.dirname(db_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            conn = init_table(duckdb.connect(db_path))
            _connections[db_path] = conn
        return conn


def _clear_connection_cache() -> None:
    with _connections_lock:
        _connections.clear()


_connection.cache_clear = _clear_connection_cache


def get_db_connection() -> duckdb.DuckDBPyConnection:
    settings = get_settings()
    return _connection(settings.duckdb_path)


def insert_event(
    conn: duckdb.DuckDBPyConnection,
    prefix: str,
    selected: str,
    action: str,
    event_ts: datetime,
) -> None:
    with _write_lock:
        conn.execute(
            "INSERT INTO search_events (prefix, selected, action, event_ts) VALUES (?, ?, ?, ?)",
            [prefix, selected, action, event_ts],
        )
