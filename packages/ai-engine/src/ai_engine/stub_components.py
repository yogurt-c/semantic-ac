from __future__ import annotations

import hashlib

import numpy as np

DEFAULT_HASH_DIM = 64


class HashingEmbeddingModel:
    """`E5SmallEmbeddingModel` 실연결 전 구조 검증용 placeholder (EmbeddingModel Protocol 구현체).

    SHA-256 해시 기반 결정론적 벡터를 반환할 뿐 의미적 유사도를 반영하지 않는다.
    docker-compose ai-worker 기본값으로 사용해, 무거운 모델 다운로드 없이도
    Faiss 인덱싱/최근접 검색 파이프라인이 배포 환경에서 끝까지 동작하는지만 확인한다.
    실제 추천 품질 검증에는 사용하지 않는다 (README.md "다음 단계" 참고).
    """

    def __init__(self, dim: int = DEFAULT_HASH_DIM) -> None:
        self._dim = dim

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._hash_vector(text) for text in texts])

    def encode_query(self, text: str) -> np.ndarray:
        return self._hash_vector(text)

    def _hash_vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self._dim, dtype=np.float32)
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        for i, byte in enumerate(digest):
            vector[i % self._dim] += byte
        vector += 1e-6  # 모든 바이트가 상쇄되어 영벡터가 되는 경우 normalize_L2 0 나눗셈 방지
        return vector


class NoopKeywordGenerator:
    """Qwen2.5 LLM 실연결 전 placeholder (KeywordGenerator Protocol 구현체).

    오타/문맥 연관 후보를 생성하지 않고 항상 빈 목록을 반환한다. 실모델 연결 전까지
    pipeline.run_batch가 빈도+최신성 스코어링 결과만으로도 구조적으로 끝까지
    동작함을 보장하기 위한 최소 구현이다.
    """

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        return []
