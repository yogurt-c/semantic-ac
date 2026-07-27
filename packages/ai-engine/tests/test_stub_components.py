from __future__ import annotations

import numpy as np

from ai_engine.stub_components import DEFAULT_HASH_DIM, HashingEmbeddingModel, NoopKeywordGenerator


def test_hashing_embedding_model_encode_query_returns_fixed_dim_vector():
    model = HashingEmbeddingModel()

    vector = model.encode_query("노트북")

    assert vector.shape == (DEFAULT_HASH_DIM,)
    assert vector.dtype == np.float32


def test_hashing_embedding_model_encode_passages_returns_matrix():
    model = HashingEmbeddingModel(dim=16)

    vectors = model.encode_passages(["노트북", "키보드", "노트북"])

    assert vectors.shape == (3, 16)
    # 동일 입력은 항상 동일 벡터 (결정론적).
    assert np.array_equal(vectors[0], vectors[2])


def test_hashing_embedding_model_distinguishes_different_texts():
    model = HashingEmbeddingModel()

    vector_a = model.encode_query("노트북")
    vector_b = model.encode_query("키보드")

    assert not np.array_equal(vector_a, vector_b)


def test_noop_keyword_generator_always_returns_empty_list():
    generator = NoopKeywordGenerator()

    assert generator.generate("노트북", ["가성비 노트북", "노트북 추천"]) == []
    assert generator.generate("", []) == []
