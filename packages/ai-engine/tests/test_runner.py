from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import fakeredis
import pytest

from ai_engine import runner as runner_module
from ai_engine.embeddings import E5SmallEmbeddingModel
from ai_engine.stub_components import HashingEmbeddingModel, NoopKeywordGenerator

_CREATE_TABLE_SQL = """
CREATE TABLE search_events (
    prefix VARCHAR,
    selected VARCHAR,
    action VARCHAR,
    event_ts TIMESTAMP,
    session_id VARCHAR
)
"""


def _seed_events_db(path: Path) -> None:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.execute(
            "INSERT INTO search_events VALUES (?, ?, ?, ?, ?)",
            ["노트북", "노트북 추천", "suggestion_click", datetime.now(timezone.utc), "session-1"],
        )
        conn.execute(
            "INSERT INTO search_events VALUES (?, ?, ?, ?, ?)",
            ["노트북", "노트북 추천", "suggestion_click", datetime.now(timezone.utc), "session-2"],
        )
    finally:
        conn.close()


def _seed_empty_events_db(path: Path) -> None:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(_CREATE_TABLE_SQL)
    finally:
        conn.close()


class _StopLoop(Exception):
    """무한 루프를 테스트 안에서 결정론적으로 끊기 위한 신호용 예외."""


def test_run_once_returns_empty_dict_when_no_events(tmp_path: Path):
    duckdb_path = tmp_path / "events.duckdb"
    _seed_empty_events_db(duckdb_path)

    written = runner_module.run_once(
        "redis://ignored", str(duckdb_path), str(tmp_path / "index.faiss")
    )

    assert written == {}


def test_run_once_raises_for_missing_duckdb_file(tmp_path: Path):
    with pytest.raises(Exception):  # noqa: B017 - duckdb 내부 예외 타입에 결합하지 않음
        runner_module.run_once(
            "redis://ignored", str(tmp_path / "missing.duckdb"), str(tmp_path / "index.faiss")
        )


def test_run_once_writes_suggestions_using_stub_components(tmp_path: Path, monkeypatch):
    duckdb_path = tmp_path / "events.duckdb"
    _seed_events_db(duckdb_path)
    fake_client = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(
        runner_module.redis.Redis, "from_url", staticmethod(lambda *args, **kwargs: fake_client)
    )

    written = runner_module.run_once(
        "redis://ignored", str(duckdb_path), str(tmp_path / "index.faiss")
    )

    assert "노트북" in written
    assert written["노트북"]
    assert json.loads(fake_client.get("sugg:노트북")) == written["노트북"]


def test_main_once_propagates_exception(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(runner_module, "run_once", _raise)

    with pytest.raises(RuntimeError, match="boom"):
        runner_module.main(["--once"])


def test_main_loop_swallows_exception_and_retries(monkeypatch, caplog: pytest.LogCaptureFixture):
    call_count = 0

    def _raise(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("boom")

    def _stop_sleep(seconds: int) -> None:
        raise _StopLoop()

    monkeypatch.setattr(runner_module, "run_once", _raise)
    monkeypatch.setattr(runner_module.time, "sleep", _stop_sleep)

    with caplog.at_level("ERROR", logger="ai_engine.runner"):
        with pytest.raises(_StopLoop):
            runner_module.main([])

    assert call_count == 1
    assert any("batch cycle failed" in record.message for record in caplog.records)


def test_main_once_passes_tuning_env_vars_through_to_run_batch(monkeypatch, tmp_path: Path):
    duckdb_path = tmp_path / "events.duckdb"
    _seed_events_db(duckdb_path)
    monkeypatch.setenv("DUCKDB_PATH", str(duckdb_path))
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.faiss"))
    monkeypatch.setenv("SUGGESTION_TOP_N", "3")
    monkeypatch.setenv("FAISS_CONTEXT_SIZE", "2")
    monkeypatch.setenv("COOCCURRENCE_HALF_LIFE_HOURS", "12")
    monkeypatch.setenv("COOCCURRENCE_SEED_SIZE", "1")
    monkeypatch.setenv("SUGGESTION_MIN_COUNT", "2")
    monkeypatch.setenv("SUGGESTION_MIN_LEN", "3")
    monkeypatch.setenv("SUGGESTION_MAX_LEN", "30")
    monkeypatch.setenv("SUGGESTION_GENERATED_MAX_SHARE", "0.5")

    captured_kwargs: dict = {}

    def _fake_run_batch(events, embedding_model, keyword_generator, redis_client, index_path, **kwargs):
        captured_kwargs.update(kwargs)
        return {}

    monkeypatch.setattr(runner_module, "run_batch", _fake_run_batch)
    monkeypatch.setattr(
        runner_module.redis.Redis,
        "from_url",
        staticmethod(lambda *args, **kwargs: fakeredis.FakeStrictRedis(decode_responses=True)),
    )

    runner_module.main(["--once"])

    assert captured_kwargs == {
        "top_n": 3,
        "context_size": 2,
        "cooccurrence_half_life_hours": 12.0,
        "cooccurrence_seed_size": 1,
        "min_occurrences": 2,
        "min_length": 3,
        "max_length": 30,
        "blocklist": frozenset(),
        "generated_max_share": 0.5,
    }


def test_main_once_uses_pipeline_defaults_when_tuning_env_vars_are_unset(monkeypatch, tmp_path: Path):
    duckdb_path = tmp_path / "events.duckdb"
    _seed_events_db(duckdb_path)
    monkeypatch.setenv("DUCKDB_PATH", str(duckdb_path))
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.faiss"))

    captured_kwargs: dict = {}

    def _fake_run_batch(events, embedding_model, keyword_generator, redis_client, index_path, **kwargs):
        captured_kwargs.update(kwargs)
        return {}

    monkeypatch.setattr(runner_module, "run_batch", _fake_run_batch)
    monkeypatch.setattr(
        runner_module.redis.Redis,
        "from_url",
        staticmethod(lambda *args, **kwargs: fakeredis.FakeStrictRedis(decode_responses=True)),
    )

    runner_module.main(["--once"])

    assert captured_kwargs == {
        "top_n": runner_module.DEFAULT_TOP_N,
        "context_size": runner_module.DEFAULT_CONTEXT_SIZE,
        "cooccurrence_half_life_hours": runner_module.DEFAULT_COOCCURRENCE_HALF_LIFE_HOURS,
        "cooccurrence_seed_size": runner_module.DEFAULT_COOCCURRENCE_SEED_SIZE,
        "min_occurrences": runner_module.DEFAULT_MIN_OCCURRENCES,
        "min_length": runner_module.DEFAULT_MIN_LENGTH,
        "max_length": runner_module.DEFAULT_MAX_LENGTH,
        "blocklist": frozenset(),
        "generated_max_share": runner_module.DEFAULT_GENERATED_MAX_SHARE,
    }


def test_main_once_loads_blocklist_from_path_env_var(monkeypatch, tmp_path: Path):
    duckdb_path = tmp_path / "events.duckdb"
    _seed_events_db(duckdb_path)
    blocklist_path = tmp_path / "blocklist.txt"
    blocklist_path.write_text("스팸단어\n", encoding="utf-8")
    monkeypatch.setenv("DUCKDB_PATH", str(duckdb_path))
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.faiss"))
    monkeypatch.setenv("SUGGESTION_BLOCKLIST_PATH", str(blocklist_path))

    captured_kwargs: dict = {}

    def _fake_run_batch(events, embedding_model, keyword_generator, redis_client, index_path, **kwargs):
        captured_kwargs.update(kwargs)
        return {}

    monkeypatch.setattr(runner_module, "run_batch", _fake_run_batch)
    monkeypatch.setattr(
        runner_module.redis.Redis,
        "from_url",
        staticmethod(lambda *args, **kwargs: fakeredis.FakeStrictRedis(decode_responses=True)),
    )

    runner_module.main(["--once"])

    assert captured_kwargs["blocklist"] == frozenset({"스팸단어"})


def test_build_embedding_model_defaults_to_hashing(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)

    model = runner_module.build_embedding_model()

    assert isinstance(model, HashingEmbeddingModel)


def test_build_embedding_model_returns_e5_when_provider_env_var_set(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "e5")
    monkeypatch.setenv("E5_MODEL_NAME", "custom/multilingual-model")

    model = runner_module.build_embedding_model()

    assert isinstance(model, E5SmallEmbeddingModel)
    assert model.model_name == "custom/multilingual-model"
    assert model.is_loaded is False


def test_build_embedding_model_raises_for_unknown_provider(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "bogus")

    with pytest.raises(ValueError, match="bogus"):
        runner_module.build_embedding_model()


def test_build_keyword_generator_defaults_to_noop(monkeypatch):
    monkeypatch.delenv("KEYWORD_GENERATOR_PROVIDER", raising=False)

    generator = runner_module.build_keyword_generator()

    assert isinstance(generator, NoopKeywordGenerator)


def test_build_keyword_generator_returns_qwen_when_provider_env_var_set(monkeypatch):
    captured_kwargs: dict = {}

    class _FakeQwenKeywordGenerator:
        def __init__(
            self, model_path: str, *, n_ctx: int, max_tokens: int, use_chat_template: bool
        ) -> None:
            captured_kwargs["model_path"] = model_path
            captured_kwargs["n_ctx"] = n_ctx
            captured_kwargs["max_tokens"] = max_tokens
            captured_kwargs["use_chat_template"] = use_chat_template

    monkeypatch.setattr(runner_module, "QwenKeywordGenerator", _FakeQwenKeywordGenerator)
    monkeypatch.setenv("KEYWORD_GENERATOR_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_MODEL_PATH", "/models/qwen.gguf")
    monkeypatch.setenv("QWEN_N_CTX", "256")
    monkeypatch.setenv("QWEN_MAX_TOKENS", "32")
    monkeypatch.setenv("QWEN_USE_CHAT_TEMPLATE", "true")

    generator = runner_module.build_keyword_generator()

    assert isinstance(generator, _FakeQwenKeywordGenerator)
    assert captured_kwargs == {
        "model_path": "/models/qwen.gguf",
        "n_ctx": 256,
        "max_tokens": 32,
        "use_chat_template": True,
    }


def test_build_keyword_generator_uses_defaults_when_optional_qwen_env_vars_unset(monkeypatch):
    captured_kwargs: dict = {}

    class _FakeQwenKeywordGenerator:
        def __init__(
            self, model_path: str, *, n_ctx: int, max_tokens: int, use_chat_template: bool
        ) -> None:
            captured_kwargs["model_path"] = model_path
            captured_kwargs["n_ctx"] = n_ctx
            captured_kwargs["max_tokens"] = max_tokens
            captured_kwargs["use_chat_template"] = use_chat_template

    monkeypatch.setattr(runner_module, "QwenKeywordGenerator", _FakeQwenKeywordGenerator)
    monkeypatch.setenv("KEYWORD_GENERATOR_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_MODEL_PATH", "/models/qwen.gguf")
    monkeypatch.delenv("QWEN_N_CTX", raising=False)
    monkeypatch.delenv("QWEN_MAX_TOKENS", raising=False)
    monkeypatch.delenv("QWEN_USE_CHAT_TEMPLATE", raising=False)

    runner_module.build_keyword_generator()

    assert captured_kwargs["n_ctx"] == runner_module.DEFAULT_QWEN_N_CTX
    assert captured_kwargs["max_tokens"] == runner_module.DEFAULT_QWEN_MAX_TOKENS
    assert captured_kwargs["use_chat_template"] is False


def test_build_keyword_generator_raises_when_qwen_model_path_missing(monkeypatch):
    monkeypatch.setenv("KEYWORD_GENERATOR_PROVIDER", "qwen")
    monkeypatch.delenv("QWEN_MODEL_PATH", raising=False)

    with pytest.raises(KeyError):
        runner_module.build_keyword_generator()


def test_build_keyword_generator_raises_for_unknown_provider(monkeypatch):
    monkeypatch.setenv("KEYWORD_GENERATOR_PROVIDER", "bogus")

    with pytest.raises(ValueError, match="bogus"):
        runner_module.build_keyword_generator()


def test_main_once_builds_and_passes_configured_components_to_run_batch(monkeypatch, tmp_path: Path):
    duckdb_path = tmp_path / "events.duckdb"
    _seed_events_db(duckdb_path)
    monkeypatch.setenv("DUCKDB_PATH", str(duckdb_path))
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.faiss"))
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("KEYWORD_GENERATOR_PROVIDER", raising=False)

    captured_args: list = []

    def _fake_run_batch(events, embedding_model, keyword_generator, redis_client, index_path, **kwargs):
        captured_args.extend([embedding_model, keyword_generator])
        return {}

    monkeypatch.setattr(runner_module, "run_batch", _fake_run_batch)
    monkeypatch.setattr(
        runner_module.redis.Redis,
        "from_url",
        staticmethod(lambda *args, **kwargs: fakeredis.FakeStrictRedis(decode_responses=True)),
    )

    runner_module.main(["--once"])

    assert isinstance(captured_args[0], HashingEmbeddingModel)
    assert isinstance(captured_args[1], NoopKeywordGenerator)


def test_main_uses_batch_interval_seconds_env_var(monkeypatch):
    captured_interval: list[int] = []

    def _stop_sleep(seconds: int) -> None:
        captured_interval.append(seconds)
        raise _StopLoop()

    monkeypatch.setattr(runner_module, "run_once", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner_module.time, "sleep", _stop_sleep)
    monkeypatch.setenv("BATCH_INTERVAL_SECONDS", "5")

    with pytest.raises(_StopLoop):
        runner_module.main([])

    assert captured_interval == [5]
