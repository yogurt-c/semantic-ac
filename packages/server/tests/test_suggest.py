import json

from fastapi.testclient import TestClient

from search_server.main import create_app
from search_server.redis_client import get_redis_client


def test_returns_suggestions_from_redis_json_array(client, fake_redis):
    fake_redis.set("sugg:노트북", json.dumps(["노트북 추천", "가성비 노트북"]))

    response = client.get("/suggest", params={"q": "노트북"})

    assert response.status_code == 200
    assert response.json() == {"suggestions": ["노트북 추천", "가성비 노트북"]}


def test_returns_empty_array_when_key_missing(client):
    response = client.get("/suggest", params={"q": "없는프리픽스"})

    assert response.status_code == 200
    assert response.json() == {"suggestions": []}


def test_returns_400_when_q_param_missing(client):
    response = client.get("/suggest")

    assert response.status_code == 400
    assert response.json() == {"error": "q is required"}


def test_returns_400_when_q_is_empty_string(client):
    response = client.get("/suggest", params={"q": ""})

    assert response.status_code == 400
    assert response.json() == {"error": "q is required"}


def test_returns_500_with_generic_message_when_redis_lookup_fails(caplog):
    class FailingRedisClient:
        def get(self, key: str) -> str:
            raise ConnectionError("redis unavailable: password leaked in this message")

    app = create_app()
    app.dependency_overrides[get_redis_client] = lambda: FailingRedisClient()

    with caplog.at_level("ERROR"):
        with TestClient(app) as test_client:
            response = test_client.get("/suggest", params={"q": "노트북"})

    assert response.status_code == 500
    assert response.json() == {"error": "internal server error"}
    assert "redis unavailable" not in response.text
    assert "redis unavailable" in caplog.text


def test_returns_500_when_redis_value_is_corrupted_json(caplog):
    class CorruptedRedisClient:
        def get(self, key: str) -> str:
            return "{not valid json"

    app = create_app()
    app.dependency_overrides[get_redis_client] = lambda: CorruptedRedisClient()

    with caplog.at_level("ERROR"):
        with TestClient(app) as test_client:
            response = test_client.get("/suggest", params={"q": "노트북"})

    assert response.status_code == 500
    assert response.json() == {"error": "internal server error"}
    assert len(caplog.records) >= 1


def test_returns_400_when_q_exceeds_max_length(client):
    too_long = "a" * 201

    response = client.get("/suggest", params={"q": too_long})

    assert response.status_code == 400
    assert response.json() == {"error": "q is too long"}
