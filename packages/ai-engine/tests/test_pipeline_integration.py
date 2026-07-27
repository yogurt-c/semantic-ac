from __future__ import annotations

import json
from pathlib import Path

import fakeredis
import pytest

from ai_engine.pipeline import run_batch


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


class _FailingKeywordGenerator:
    """특정 prefix에서만 예외를 던져 부분 실패 시나리오를 재현하는 테스트용 더블."""

    def __init__(self, fail_on_prefix: str) -> None:
        self._fail_on_prefix = fail_on_prefix

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        if prefix == self._fail_on_prefix:
            raise RuntimeError("boom")
        return [f"{prefix}추천", *context[:2]]


def test_run_batch_logs_and_keeps_previously_written_prefixes_on_partial_failure(
    sample_events, fake_embedding_model, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    index_path = tmp_path / "batch.faiss"
    failing_generator = _FailingKeywordGenerator(fail_on_prefix="키보드")

    with caplog.at_level("ERROR", logger="ai_engine.pipeline"):
        with pytest.raises(RuntimeError):
            run_batch(sample_events, fake_embedding_model, failing_generator, redis_client, index_path)

    assert json.loads(redis_client.get("sugg:노트북")) is not None
    assert redis_client.get("sugg:키보드") is None
    assert any("키보드" in record.message for record in caplog.records)
