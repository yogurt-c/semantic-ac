from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import fakeredis
import pytest

from ai_engine import pipeline as pipeline_module
from ai_engine.events import SearchEvent
from ai_engine.pipeline import run_batch
from ai_engine.redis_writer import write_suggestions as real_write_suggestions


def test_run_batch_writes_suggestions_for_every_prefix(
    sample_events, fake_embedding_model, fake_keyword_generator, tmp_path: Path
):
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    index_path = tmp_path / "batch.faiss"

    written = run_batch(
        sample_events,
        fake_embedding_model,
        fake_keyword_generator,
        redis_client,
        index_path,
    )

    assert set(written.keys()) == {"노트북", "키보드"}
    for prefix, suggestions in written.items():
        stored = json.loads(redis_client.get(f"sugg:{prefix}"))
        assert stored == suggestions
        assert len(suggestions) > 0

    assert index_path.exists()


def test_run_batch_returns_empty_dict_for_no_events(
    fake_embedding_model, fake_keyword_generator, tmp_path: Path
):
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)

    written = run_batch(
        [], fake_embedding_model, fake_keyword_generator, redis_client, tmp_path / "idx.faiss"
    )

    assert written == {}
    assert not (tmp_path / "idx.faiss").exists()


def test_run_batch_replaces_previous_index_atomically(
    sample_events, fake_embedding_model, fake_keyword_generator, tmp_path: Path
):
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    index_path = tmp_path / "batch.faiss"
    index_path.write_bytes(b"stale-index")

    run_batch(sample_events, fake_embedding_model, fake_keyword_generator, redis_client, index_path)

    assert index_path.read_bytes() != b"stale-index"


def test_run_batch_deduplicates_scored_and_generated_suggestions(
    sample_events, fake_embedding_model, fake_keyword_generator, tmp_path: Path
):
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    index_path = tmp_path / "batch.faiss"

    written = run_batch(
        sample_events,
        fake_embedding_model,
        fake_keyword_generator,
        redis_client,
        index_path,
    )

    for suggestions in written.values():
        assert len(suggestions) == len(set(suggestions))


def test_run_batch_surfaces_cooccurring_term_from_a_different_prefix(
    fake_embedding_model, fake_keyword_generator, tmp_path: Path
):
    """세션 co-occurrence 레이어 검증: "노"와 "맥"은 prefix도, 문자열도 겹치지 않지만
    같은 세션에서 "노트북"과 "맥북"이 함께 selected됐다면 서로의 추천 목록에 나타나야 한다."""
    now = datetime.now(timezone.utc)
    events = [
        SearchEvent(
            prefix="노", selected="노트북", action="final_search", event_ts=now, session_id="s1"
        ),
        SearchEvent(
            prefix="맥", selected="맥북", action="final_search", event_ts=now, session_id="s1"
        ),
    ]
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)

    written = run_batch(
        events, fake_embedding_model, fake_keyword_generator, redis_client, tmp_path / "idx.faiss"
    )

    assert "맥북" in written["노"]
    assert "노트북" in written["맥"]


class _FailingKeywordGenerator:
    """특정 prefix에서만 예외를 던지는 테스트용 더블.

    run_batch가 주입받은 keyword_generator를 항상 GuardedKeywordGenerator로
    감싸기 때문에(guarded_keyword_generator.py), 이 예외는 배치를 중단시키지
    않고 빈 리스트로 흡수되어야 한다 — 아래
    test_run_batch_continues_when_keyword_generator_raises_for_one_prefix 참고.
    """

    def __init__(self, fail_on_prefix: str) -> None:
        self._fail_on_prefix = fail_on_prefix

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        if prefix == self._fail_on_prefix:
            raise RuntimeError("boom")
        return [f"{prefix}추천", *context[:2]]


def test_run_batch_continues_when_keyword_generator_raises_for_one_prefix(
    sample_events, fake_embedding_model, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    index_path = tmp_path / "batch.faiss"
    failing_generator = _FailingKeywordGenerator(fail_on_prefix="키보드")

    with caplog.at_level("ERROR", logger="ai_engine.guarded_keyword_generator"):
        written = run_batch(sample_events, fake_embedding_model, failing_generator, redis_client, index_path)

    assert set(written.keys()) == {"노트북", "키보드"}
    assert len(written["키보드"]) > 0  # scoring 레이어는 LLM 레이어 실패와 무관하게 채워짐
    assert any("키보드" in record.message for record in caplog.records)


def test_run_batch_logs_and_keeps_previously_written_prefixes_on_partial_failure(
    sample_events,
    fake_embedding_model,
    fake_keyword_generator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """keyword_generator 실패는 이제 가드레일이 흡수하므로, 여기서는 Redis 쓰기
    자체가 실패하는 시나리오로 배치 레벨 부분 실패/재전파 계약을 검증한다."""
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    index_path = tmp_path / "batch.faiss"

    def _failing_write(client, prefix, suggestions):
        if prefix == "키보드":
            raise RuntimeError("boom")
        real_write_suggestions(client, prefix, suggestions)

    monkeypatch.setattr(pipeline_module, "write_suggestions", _failing_write)

    with caplog.at_level("ERROR", logger="ai_engine.pipeline"):
        with pytest.raises(RuntimeError):
            run_batch(sample_events, fake_embedding_model, fake_keyword_generator, redis_client, index_path)

    assert json.loads(redis_client.get("sugg:노트북")) is not None
    assert redis_client.get("sugg:키보드") is None
    assert any("키보드" in record.message for record in caplog.records)


class _NoisyKeywordGenerator:
    """seed와 무관하지 않지만 정제 대상인 후보(불용어/숫자만)를 섞어 반환한다."""

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        return ["그냥", f"{prefix} 정품", "12345"]


def test_run_batch_filters_noise_out_of_generated_candidates(
    sample_events, fake_embedding_model, tmp_path: Path
):
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)

    written = run_batch(
        sample_events, fake_embedding_model, _NoisyKeywordGenerator(), redis_client, tmp_path / "idx.faiss"
    )

    assert "그냥" not in written["노트북"]
    assert "12345" not in written["노트북"]
    assert "노트북 정품" in written["노트북"]


def test_run_batch_respects_blocklist_parameter(
    sample_events, fake_embedding_model, tmp_path: Path
):
    class _EchoGenerator:
        def generate(self, prefix: str, context: list[str]) -> list[str]:
            return [f"{prefix} 정품"]

    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)

    written = run_batch(
        sample_events,
        fake_embedding_model,
        _EchoGenerator(),
        redis_client,
        tmp_path / "idx.faiss",
        blocklist=frozenset({"노트북 정품".casefold()}),
    )

    assert "노트북 정품" not in written["노트북"]


def test_run_batch_caps_generated_layer_contribution(
    sample_events, fake_embedding_model, tmp_path: Path
):
    class _ManyCandidatesGenerator:
        def generate(self, prefix: str, context: list[str]) -> list[str]:
            return [f"{prefix}후보{i}" for i in range(10)]

    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)

    written = run_batch(
        sample_events,
        fake_embedding_model,
        _ManyCandidatesGenerator(),
        redis_client,
        tmp_path / "idx.faiss",
        top_n=10,
        generated_max_share=0.3,
    )

    generated_terms = {f"노트북후보{i}" for i in range(10)}
    contributed = [term for term in written["노트북"] if term in generated_terms]
    assert len(contributed) <= 3


def test_run_batch_applies_min_occurrences_to_prefix_ranking(
    fake_embedding_model, tmp_path: Path, reference_time
):
    """min_occurrences는 scoring(빈도) 레이어를 걸러낸다. 여기서는 KeywordGenerator를
    항상 빈 리스트를 반환하는 더블로 고정해, Faiss context-echo 같은 별개
    채널(의미적 유사도, 빈도와 무관)이 결과에 섞이지 않게 격리한다."""

    class _EmptyGenerator:
        def generate(self, prefix: str, context: list[str]) -> list[str]:
            return []

    events = [
        SearchEvent(
            prefix="노트북", selected="노트북 추천", action="final_search", event_ts=reference_time
        ),
        SearchEvent(
            prefix="노트북", selected="희귀검색어", action="final_search", event_ts=reference_time
        ),
    ]
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)

    written = run_batch(
        events,
        fake_embedding_model,
        _EmptyGenerator(),
        redis_client,
        tmp_path / "idx.faiss",
        min_occurrences=2,
    )

    assert "희귀검색어" not in written["노트북"]
