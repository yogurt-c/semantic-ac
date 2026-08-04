from __future__ import annotations

import difflib
import logging

from ai_engine.candidate_filters import DEFAULT_STOPWORDS, clean_candidates
from ai_engine.keyword_generator import KeywordGenerator

logger = logging.getLogger(__name__)

DEFAULT_SEED_SIMILARITY_THRESHOLD = 0.3


class GuardedKeywordGenerator:
    """어떤 KeywordGenerator 구현체를 감싸도 안전한 출력만 내보내는 가드레일.

    LLM 생성기는 로그 기반 레이어(scoring/cooccurrence)와 달리 "실제로 검색된
    적 없는" 문자열을 새로 만들어내므로, 모델을 무엇으로 교체하든 아래 네 가지가
    항상 보장되도록 pipeline.run_batch가 주입받은 KeywordGenerator를 항상 이
    래퍼로 감싼 뒤에만 사용한다:

    1. 예외/타임아웃/형식 오류 시 빈 리스트로 안전 폴백 (부분 오염 통과 없음)
    2. 반환값이 list[str]이 아니면 형식 오류로 간주해 폐기
    3. seed(prefix + context)와 무관한 환각(hallucination) 후보를 편집거리 기준으로 폐기
    4. 나머지 레이어와 동일한 정제 필터(불용어/길이/특수문자·숫자만/블록리스트) 재적용
    """

    def __init__(
        self,
        inner: KeywordGenerator,
        *,
        similarity_threshold: float = DEFAULT_SEED_SIMILARITY_THRESHOLD,
        blocklist: frozenset[str] = frozenset(),
    ) -> None:
        self._inner = inner
        self._similarity_threshold = similarity_threshold
        self._blocklist = blocklist

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        try:
            raw = self._inner.generate(prefix, context)
        except Exception:
            logger.exception(
                "keyword generator raised; falling back to empty list (prefix=%r)", prefix
            )
            return []

        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            logger.warning(
                "keyword generator returned malformed output; discarding (prefix=%r)", prefix
            )
            return []

        seeds = [prefix, *context]
        seed_related = [candidate for candidate in raw if self._is_seed_related(candidate, seeds)]

        return clean_candidates(seed_related, stopwords=DEFAULT_STOPWORDS, blocklist=self._blocklist)

    def _is_seed_related(self, candidate: str, seeds: list[str]) -> bool:
        if not seeds:
            return True
        best_ratio = max(difflib.SequenceMatcher(None, candidate, seed).ratio() for seed in seeds)
        return best_ratio >= self._similarity_threshold
