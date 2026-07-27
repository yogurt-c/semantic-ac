from __future__ import annotations

import json

import fakeredis

from ai_engine.redis_writer import suggestion_key, write_suggestions


def test_suggestion_key_uses_contract_prefix():
    assert suggestion_key("노트북") == "sugg:노트북"


def test_write_suggestions_sets_json_array():
    client = fakeredis.FakeStrictRedis(decode_responses=True)

    write_suggestions(client, "노트북", ["노트북 추천", "가성비 노트북"])

    stored = client.get("sugg:노트북")
    assert json.loads(stored) == ["노트북 추천", "가성비 노트북"]


def test_write_suggestions_overwrites_previous_value_atomically():
    client = fakeredis.FakeStrictRedis(decode_responses=True)

    write_suggestions(client, "노트북", ["old"])
    write_suggestions(client, "노트북", ["new"])

    assert json.loads(client.get("sugg:노트북")) == ["new"]


def test_write_suggestions_handles_empty_list():
    client = fakeredis.FakeStrictRedis(decode_responses=True)

    write_suggestions(client, "없음", [])

    assert json.loads(client.get("sugg:없음")) == []
