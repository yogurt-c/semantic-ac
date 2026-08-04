from __future__ import annotations

import pytest

from ai_engine.guarded_keyword_generator import GuardedKeywordGenerator


class _RaisingGenerator:
    def generate(self, prefix: str, context: list[str]) -> list[str]:
        raise RuntimeError("model timeout")


class _MalformedGenerator:
    def generate(self, prefix: str, context: list[str]):  # noqa: ANN201 - 의도적으로 잘못된 타입 반환
        return "not-a-list"


class _MixedTypeGenerator:
    def generate(self, prefix: str, context: list[str]) -> list:
        return ["노트북 추천", 42]


class _EchoGenerator:
    def __init__(self, candidates: list[str]) -> None:
        self._candidates = candidates

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        return self._candidates


def test_falls_back_to_empty_list_when_inner_generator_raises(caplog: pytest.LogCaptureFixture):
    guarded = GuardedKeywordGenerator(_RaisingGenerator())

    with caplog.at_level("ERROR", logger="ai_engine.guarded_keyword_generator"):
        result = guarded.generate("노트북", ["노트북 추천"])

    assert result == []
    assert any("keyword generator raised" in record.message for record in caplog.records)


def test_falls_back_to_empty_list_when_inner_generator_returns_non_list():
    guarded = GuardedKeywordGenerator(_MalformedGenerator())

    assert guarded.generate("노트북", ["노트북 추천"]) == []


def test_falls_back_to_empty_list_when_inner_generator_returns_non_str_items():
    guarded = GuardedKeywordGenerator(_MixedTypeGenerator())

    assert guarded.generate("노트북", ["노트북 추천"]) == []


def test_keeps_candidates_closely_related_to_seed():
    guarded = GuardedKeywordGenerator(_EchoGenerator(["노트북 추천"]))

    result = guarded.generate("노트북", ["노트북 케이스"])

    assert result == ["노트북 추천"]


def test_discards_candidates_unrelated_to_seed():
    guarded = GuardedKeywordGenerator(_EchoGenerator(["완전히 무관한 긴 문장입니다"]))

    result = guarded.generate("노트북", ["노트북 추천"])

    assert result == []


def test_applies_common_clean_filter_to_generator_output():
    """"그냥"은 prefix/context와 편집거리가 가까워 seed 근접성 검사는 통과하지만,
    불용어라서 clean_candidates 단계에서 별도로 걸러져야 한다."""
    guarded = GuardedKeywordGenerator(_EchoGenerator(["노트북 추천", "그냥"]))

    result = guarded.generate("그냥", ["노트북"])

    assert result == ["노트북 추천"]


def test_applies_blocklist_to_generator_output():
    guarded = GuardedKeywordGenerator(
        _EchoGenerator(["노트북 추천", "노트북스팸"]), blocklist=frozenset({"노트북스팸"})
    )

    result = guarded.generate("노트북", [])

    assert result == ["노트북 추천"]


def test_returns_empty_list_when_inner_generator_returns_empty_list():
    guarded = GuardedKeywordGenerator(_EchoGenerator([]))

    assert guarded.generate("노트북", ["노트북 추천"]) == []
