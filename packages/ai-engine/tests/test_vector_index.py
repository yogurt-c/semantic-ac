from __future__ import annotations

from pathlib import Path

import pytest

from ai_engine.vector_index import (
    build_index,
    load_index,
    nearest_keywords,
    save_index_atomic,
)


def test_build_index_returns_index_with_matching_count(fake_embedding_model):
    keywords = ["노트북 추천", "가성비 노트북", "기계식 키보드"]
    index = build_index(keywords, fake_embedding_model)
    assert index.ntotal == 3


def test_build_index_uses_passage_encoding_not_query_encoding(fake_embedding_model):
    keywords = ["노트북 추천", "가성비 노트북"]
    build_index(keywords, fake_embedding_model)

    assert fake_embedding_model.passage_calls == [keywords]
    assert fake_embedding_model.query_calls == []


def test_build_index_rejects_empty_keywords(fake_embedding_model):
    with pytest.raises(ValueError):
        build_index([], fake_embedding_model)


def test_save_index_atomic_writes_loadable_index(tmp_path: Path, fake_embedding_model):
    index_path = tmp_path / "index.faiss"

    index = build_index(["a", "b"], fake_embedding_model)
    save_index_atomic(index, index_path)

    loaded = load_index(index_path)
    assert loaded.ntotal == 2


def test_save_index_atomic_replaces_existing_file(tmp_path: Path, fake_embedding_model):
    index_path = tmp_path / "index.faiss"
    index_path.write_bytes(b"old-data")

    index = build_index(["a", "b", "c"], fake_embedding_model)
    save_index_atomic(index, index_path)

    loaded = load_index(index_path)
    assert loaded.ntotal == 3


def test_save_index_atomic_cleans_up_tmp_file_on_write_failure(
    tmp_path: Path, fake_embedding_model, monkeypatch
):
    import ai_engine.vector_index as vector_index_module

    index_path = tmp_path / "index.faiss"
    index_path.write_bytes(b"original")

    def boom(*_args, **_kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(vector_index_module.faiss, "write_index", boom)

    index = build_index(["a", "b"], fake_embedding_model)
    with pytest.raises(RuntimeError):
        save_index_atomic(index, index_path)

    assert index_path.read_bytes() == b"original"
    assert list(tmp_path.glob("*.tmp")) == []


def test_nearest_keywords_returns_requested_count(fake_embedding_model):
    vocabulary = ["노트북 추천", "가성비 노트북", "기계식 키보드", "무선 마우스"]
    index = build_index(vocabulary, fake_embedding_model)

    results = nearest_keywords(index, vocabulary, fake_embedding_model, "노트북 추천", top_k=2)

    assert len(results) == 2
    assert all(keyword in vocabulary for keyword in results)


def test_nearest_keywords_caps_top_k_to_index_size(fake_embedding_model):
    vocabulary = ["노트북 추천", "가성비 노트북"]
    index = build_index(vocabulary, fake_embedding_model)

    results = nearest_keywords(index, vocabulary, fake_embedding_model, "노트북 추천", top_k=10)

    assert len(results) == 2


def test_nearest_keywords_uses_query_encoding_not_passage_encoding(fake_embedding_model):
    vocabulary = ["노트북 추천", "가성비 노트북"]
    index = build_index(vocabulary, fake_embedding_model)
    fake_embedding_model.passage_calls.clear()

    nearest_keywords(index, vocabulary, fake_embedding_model, "노트북 추천", top_k=1)

    assert fake_embedding_model.query_calls == ["노트북 추천"]
    assert fake_embedding_model.passage_calls == []


@pytest.mark.parametrize("invalid_top_k", [0, -1, -5])
def test_nearest_keywords_rejects_non_positive_top_k(fake_embedding_model, invalid_top_k):
    vocabulary = ["노트북 추천", "가성비 노트북"]
    index = build_index(vocabulary, fake_embedding_model)

    with pytest.raises(ValueError):
        nearest_keywords(index, vocabulary, fake_embedding_model, "노트북 추천", top_k=invalid_top_k)
