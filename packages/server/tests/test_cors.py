from fastapi.testclient import TestClient

from search_server.config import Settings
from search_server.db import get_db_connection
from search_server.main import create_app
from search_server.redis_client import get_redis_client


def _build_client(allowed_origins: list[str], fake_redis, duckdb_conn) -> TestClient:
    app = create_app(Settings(allowed_origins=allowed_origins))
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    app.dependency_overrides[get_db_connection] = lambda: duckdb_conn
    return TestClient(app)


def test_wildcard_origin_reflects_any_requesting_origin(fake_redis, duckdb_conn):
    client = _build_client(["*"], fake_redis, duckdb_conn)

    response = client.get(
        "/suggest", params={"q": "노트북"}, headers={"Origin": "https://anywhere.example.com"}
    )

    assert response.headers["access-control-allow-origin"] == "*"


def test_configured_origin_is_allowed(fake_redis, duckdb_conn):
    client = _build_client(["https://shop.example.com"], fake_redis, duckdb_conn)

    response = client.get(
        "/suggest", params={"q": "노트북"}, headers={"Origin": "https://shop.example.com"}
    )

    assert response.headers["access-control-allow-origin"] == "https://shop.example.com"


def test_unlisted_origin_is_not_allowed(fake_redis, duckdb_conn):
    client = _build_client(["https://shop.example.com"], fake_redis, duckdb_conn)

    response = client.get(
        "/suggest", params={"q": "노트북"}, headers={"Origin": "https://evil.example.com"}
    )

    assert "access-control-allow-origin" not in response.headers


def test_preflight_allows_post_to_track_endpoint(fake_redis, duckdb_conn):
    client = _build_client(["https://shop.example.com"], fake_redis, duckdb_conn)

    response = client.options(
        "/track",
        headers={
            "Origin": "https://shop.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://shop.example.com"
