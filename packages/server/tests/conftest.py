import duckdb
import fakeredis
import pytest
from fastapi.testclient import TestClient

from search_server.db import get_db_connection, init_table
from search_server.main import create_app
from search_server.redis_client import get_redis_client


@pytest.fixture
def fake_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def duckdb_conn(tmp_path):
    conn = duckdb.connect(str(tmp_path / "search_events.duckdb"))
    init_table(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(fake_redis, duckdb_conn):
    app = create_app()
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    app.dependency_overrides[get_db_connection] = lambda: duckdb_conn
    return TestClient(app)
