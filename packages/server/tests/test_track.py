import threading
from datetime import datetime, timedelta, UTC

from fastapi.testclient import TestClient

from search_server.config import get_settings
from search_server.db import _connection
from search_server.main import create_app


def test_track_suggestion_click_returns_202_with_empty_body(client):
    response = client.post(
        "/track",
        json={"prefix": "노트북", "selected": "가성비 노트북", "action": "suggestion_click"},
    )

    assert response.status_code == 202
    assert response.content == b""


def test_track_final_search_returns_202(client):
    response = client.post(
        "/track",
        json={"prefix": "노트북", "selected": "노트북 추천", "action": "final_search"},
    )

    assert response.status_code == 202


def test_track_inserts_row_into_duckdb_with_server_set_event_ts(client, duckdb_conn):
    before = datetime.now(UTC).replace(tzinfo=None)

    client.post(
        "/track",
        json={"prefix": "노트북", "selected": "가성비 노트북", "action": "suggestion_click"},
    )

    after = datetime.now(UTC).replace(tzinfo=None)

    rows = duckdb_conn.execute(
        "SELECT prefix, selected, action, event_ts FROM search_events"
    ).fetchall()

    assert len(rows) == 1
    prefix, selected, action, event_ts = rows[0]
    assert prefix == "노트북"
    assert selected == "가성비 노트북"
    assert action == "suggestion_click"
    assert before - timedelta(seconds=1) <= event_ts <= after + timedelta(seconds=1)


def test_track_rejects_invalid_action_with_422(client):
    response = client.post(
        "/track",
        json={"prefix": "노트북", "selected": "노트북 추천", "action": "invalid_action"},
    )

    assert response.status_code == 422


def test_track_rejects_missing_required_field_with_422(client):
    response = client.post(
        "/track",
        json={"prefix": "노트북", "action": "final_search"},
    )

    assert response.status_code == 422


def test_track_ignores_client_supplied_timestamp(client, duckdb_conn):
    client.post(
        "/track",
        json={
            "prefix": "노트북",
            "selected": "노트북 추천",
            "action": "final_search",
            "timestamp": "2000-01-01T00:00:00Z",
        },
    )

    row = duckdb_conn.execute("SELECT event_ts FROM search_events").fetchone()

    assert row[0].year != 2000


def test_track_rejects_prefix_exceeding_max_length_with_422(client):
    response = client.post(
        "/track",
        json={"prefix": "a" * 201, "selected": "노트북", "action": "final_search"},
    )

    assert response.status_code == 422


def test_track_rejects_selected_exceeding_max_length_with_422(client):
    response = client.post(
        "/track",
        json={"prefix": "노트북", "selected": "a" * 201, "action": "final_search"},
    )

    assert response.status_code == 422


def test_concurrent_post_track_requests_all_succeed(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "http_concurrent.duckdb"))
    get_settings.cache_clear()
    _connection.cache_clear()

    app = create_app()
    real_client = TestClient(app)

    request_count = 20
    results: list[int] = []
    results_lock = threading.Lock()

    def send(i: int) -> None:
        response = real_client.post(
            "/track",
            json={"prefix": f"p-{i}", "selected": f"s-{i}", "action": "final_search"},
        )
        with results_lock:
            results.append(response.status_code)

    threads = [threading.Thread(target=send, args=(i,)) for i in range(request_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == [202] * request_count

    conn = _connection(str(tmp_path / "http_concurrent.duckdb"))
    count = conn.execute("SELECT COUNT(*) FROM search_events").fetchone()[0]
    assert count == request_count

    get_settings.cache_clear()
    _connection.cache_clear()
