from __future__ import annotations

import json
from pathlib import Path

from ai_engine.keyword_generator import KeywordGenerator

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "typo_synonym_pairs.json"


def test_fake_keyword_generator_conforms_to_protocol(fake_keyword_generator):
    assert isinstance(fake_keyword_generator, KeywordGenerator)


def test_fake_keyword_generator_returns_non_empty_list_of_str(fake_keyword_generator):
    result = fake_keyword_generator.generate("노트북", ["노트북 추천"])

    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(keyword, str) for keyword in result)


def test_typo_synonym_fixture_has_ten_to_twenty_pairs():
    pairs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert 10 <= len(pairs) <= 20


def test_typo_synonym_fixture_drives_structurally_valid_generator_output(
    fake_keyword_generator,
):
    pairs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    for pair in pairs:
        result = fake_keyword_generator.generate(pair["prefix"], [pair["correct"]])
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(keyword, str) for keyword in result)
