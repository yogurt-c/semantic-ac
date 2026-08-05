from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "
DEFAULT_E5_MODEL_NAME = "intfloat/multilingual-e5-small"


def _resolve_prefix(model_prompts: dict[str, str] | None, prompt_name: str, fallback: str) -> str:
    """sentence-transformers 모델이 `config_sentence_transformers.json`에 자신만의
    prompt(예: "query"/"passage")를 선언해두면 그걸 우선 쓰고, 선언이 없는 모델(e5
    계열 등)에서는 하드코딩된 e5 프리픽스로 fallback한다 — 다른 sentence-transformers
    모델로 바꿀 때 이 파일을 고치지 않아도 되게 하기 위함이다."""
    if model_prompts and prompt_name in model_prompts:
        return model_prompts[prompt_name]
    return fallback


@runtime_checkable
class EmbeddingModel(Protocol):
    """키워드 문자열을 고정 차원 벡터로 변환하는 인터페이스.

    e5 계열 모델은 인덱싱 대상(코퍼스/vocabulary)과 질의를 서로 다른 프리픽스로
    인코딩해야 검색 품질이 보장되므로, 역할별로 메서드를 분리한다.
    """

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        """인덱싱 대상 키워드 배치를 (len(texts), dim) float32 배열로 인코딩한다."""
        ...

    def encode_query(self, text: str) -> np.ndarray:
        """질의 문자열 1건을 (dim,) float32 벡터로 인코딩한다."""
        ...


class E5SmallEmbeddingModel:
    """intfloat/multilingual-e5-small 실제 통합 지점.

    가중치 다운로드가 무거우므로 생성 시점이 아닌 최초 encode_passages()/
    encode_query() 호출 시점에 sentence-transformers를 지연 임포트/로드한다.
    실제 추론 경로는 이번 작업 범위에서 테스트하지 않는다 (README의 "다음 단계" 참고).
    """

    def __init__(self, model_name: str = DEFAULT_E5_MODEL_NAME) -> None:
        self._model_name = model_name
        self._model = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def encode_passages(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - 실 모델 다운로드 필요
        self._ensure_loaded()
        prefix = _resolve_prefix(getattr(self._model, "prompts", None), "passage", E5_PASSAGE_PREFIX)
        prefixed = [f"{prefix}{text}" for text in texts]
        embeddings = self._model.encode(prefixed, normalize_embeddings=True)
        return np.asarray(embeddings, dtype=np.float32)

    def encode_query(self, text: str) -> np.ndarray:  # pragma: no cover - 실 모델 다운로드 필요
        self._ensure_loaded()
        prefix = _resolve_prefix(getattr(self._model, "prompts", None), "query", E5_QUERY_PREFIX)
        embeddings = self._model.encode([f"{prefix}{text}"], normalize_embeddings=True)
        return np.asarray(embeddings[0], dtype=np.float32)

    def _ensure_loaded(self) -> None:  # pragma: no cover - 실 모델 다운로드 필요
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
