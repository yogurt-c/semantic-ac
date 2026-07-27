from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from ai_engine.events import SearchEvent

FAKE_VECTOR_DIM = 8


class FakeEmbeddingModel:
    """고정 차원의 결정적 벡터를 반환하는 테스트용 임베딩 모델 (EmbeddingModel Protocol 구현체).

    encode_passages()/encode_query() 호출 인자를 기록해, 인덱싱 경로가 passage를
    쓰고 질의 경로가 query를 쓰는지 회귀 테스트에서 검증할 수 있게 한다.
    """

    def __init__(self, dim: int = FAKE_VECTOR_DIM) -> None:
        self._dim = dim
        self.passage_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        self.passage_calls.append(list(texts))
        return self._encode_many(texts)

    def encode_query(self, text: str) -> np.ndarray:
        self.query_calls.append(text)
        return self._encode_many([text])[0]

    def _encode_many(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self._dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for col, char in enumerate(text):
                vectors[row, col % self._dim] += ord(char)
        vectors += 1e-6  # 모든 문자가 동일해 영벡터가 되는 경우 normalize_L2 0 나눗셈 방지
        return vectors


class FakeKeywordGenerator:
    """context를 참고해 결정적으로 후보를 만드는 테스트용 KeywordGenerator Protocol 구현체."""

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        candidates = [f"{prefix}추천"]
        candidates.extend(context[:2])
        return candidates


@pytest.fixture
def fake_embedding_model() -> FakeEmbeddingModel:
    return FakeEmbeddingModel()


@pytest.fixture
def fake_keyword_generator() -> FakeKeywordGenerator:
    return FakeKeywordGenerator()


@pytest.fixture
def reference_time() -> datetime:
    return datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_events(reference_time: datetime) -> list[SearchEvent]:
    return [
        SearchEvent(
            prefix="노트북",
            selected="노트북 추천",
            action="suggestion_click",
            event_ts=reference_time - timedelta(hours=1),
        ),
        SearchEvent(
            prefix="노트북",
            selected="가성비 노트북",
            action="final_search",
            event_ts=reference_time - timedelta(hours=48),
        ),
        SearchEvent(
            prefix="노트북",
            selected="노트북 추천",
            action="suggestion_click",
            event_ts=reference_time - timedelta(hours=2),
        ),
        SearchEvent(
            prefix="키보드",
            selected="기계식 키보드",
            action="final_search",
            event_ts=reference_time - timedelta(minutes=30),
        ),
    ]
