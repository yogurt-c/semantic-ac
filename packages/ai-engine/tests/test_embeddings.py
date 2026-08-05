from __future__ import annotations

import numpy as np

from ai_engine.embeddings import (
    E5_PASSAGE_PREFIX,
    E5_QUERY_PREFIX,
    E5SmallEmbeddingModel,
    EmbeddingModel,
    _resolve_prefix,
)


def test_fake_embedding_model_conforms_to_protocol(fake_embedding_model):
    assert isinstance(fake_embedding_model, EmbeddingModel)


def test_fake_embedding_model_encode_passages_returns_matrix_shaped_by_input(
    fake_embedding_model,
):
    vectors = fake_embedding_model.encode_passages(["a", "bb", "ccc"])
    assert vectors.shape == (3, 8)
    assert vectors.dtype == np.float32


def test_fake_embedding_model_encode_query_returns_single_vector(fake_embedding_model):
    vector = fake_embedding_model.encode_query("노트북 추천")
    assert vector.shape == (8,)
    assert vector.dtype == np.float32


def test_e5_small_model_conforms_to_protocol():
    assert isinstance(E5SmallEmbeddingModel(), EmbeddingModel)


def test_e5_small_model_does_not_load_weights_until_encode_is_called():
    model = E5SmallEmbeddingModel()
    assert model.is_loaded is False
    assert model.model_name == "intfloat/multilingual-e5-small"


def test_resolve_prefix_uses_model_declared_prompt_when_present():
    prefix = _resolve_prefix({"query": "Instruct: search\nQuery: "}, "query", E5_QUERY_PREFIX)
    assert prefix == "Instruct: search\nQuery: "


def test_resolve_prefix_falls_back_to_default_when_model_has_no_prompts():
    prefix = _resolve_prefix(None, "query", E5_QUERY_PREFIX)
    assert prefix == E5_QUERY_PREFIX


def test_resolve_prefix_falls_back_when_prompt_name_not_declared():
    prefix = _resolve_prefix({"other": "..."}, "passage", E5_PASSAGE_PREFIX)
    assert prefix == E5_PASSAGE_PREFIX
