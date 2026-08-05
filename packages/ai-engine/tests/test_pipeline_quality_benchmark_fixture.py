from __future__ import annotations

import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pipeline_quality_benchmark.json"


def _load_pairs() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_has_a_reasonably_sized_sample():
    pairs = _load_pairs()
    assert 30 <= len(pairs) <= 60


def test_fixture_entries_have_required_fields_and_valid_type():
    for pair in _load_pairs():
        assert pair["prefix"]
        assert pair["correct"]
        assert pair["type"] in {"typo", "synonym"}


def test_fixture_prefixes_are_disjoint_from_correct_answers():
    """eval_pipeline_quality.py는 prefix에 selected=prefix인 이벤트만 주입하고
    correct 값은 별도 이벤트로만 vocabulary에 심는다(콜드 스타트 가정) - 어떤
    prefix가 다른 항목의 correct와 겹치면 scoring 레이어가 우연히 정답을 알아내
    baseline이 실제보다 더 잘 맞은 것처럼 보이는 오염이 생긴다."""
    pairs = _load_pairs()
    prefixes = {pair["prefix"] for pair in pairs}
    corrects = {pair["correct"] for pair in pairs}

    assert prefixes.isdisjoint(corrects)


def test_fixture_prefixes_are_unique():
    pairs = _load_pairs()
    prefixes = [pair["prefix"] for pair in pairs]
    assert len(prefixes) == len(set(prefixes))
