import os
import threading
from collections.abc import Iterator
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

# DuckDB holds a file lock for as long as a connection stays open, regardless
# of read_only mode — an AI batch worker (a separate OS process, see
# docs/CONTRACT.md section 2) can never open the same file with
# read_only=True while this server keeps a connection cached for its whole
# process lifetime. Each request must open, write, and close its own
# connection so the lock is released between requests. The write lock still
# serializes connection creation/writes across threads within this process.
_write_lock = threading.Lock()


def init_table(conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    conn.execute(CREATE_TABLE_SQL)
    return conn


def get_db_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    settings = get_settings()
    db_path = settings.duckdb_path
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with _write_lock:
        conn = init_table(duckdb.connect(db_path))
        try:
            yield conn
        finally:
            conn.close()


def insert_event(
    conn: duckdb.DuckDBPyConnection,
    prefix: str,
    selected: str,
    action: str,
    event_ts: datetime,
) -> None:
    conn.execute(
        "INSERT INTO search_events (prefix, selected, action, event_ts) VALUES (?, ?, ?, ?)",
        [prefix, selected, action, event_ts],
    )
