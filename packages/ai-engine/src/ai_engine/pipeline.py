from __future__ import annotations

import logging
from pathlib import Path

import redis

from ai_engine.embeddings import EmbeddingModel
from ai_engine.events import SearchEvent
from ai_engine.keyword_generator import KeywordGenerator
from ai_engine.redis_writer import write_suggestions
from ai_engine.scoring import group_events_by_prefix, score_keywords
from ai_engine.vector_index import build_index, nearest_keywords, save_index_atomic

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 10
DEFAULT_CONTEXT_SIZE = 5


def run_batch(
    events: list[SearchEvent],
    embedding_model: EmbeddingModel,
    keyword_generator: KeywordGenerator,
    redis_client: redis.Redis,
    index_path: Path | str,
    *,
    top_n: int = DEFAULT_TOP_N,
    context_size: int = DEFAULT_CONTEXT_SIZE,
) -> dict[str, list[str]]:
    """스코어링 -> 임베딩/Faiss -> KeywordGenerator -> Redis 쓰기 전체 배치 1회 실행.

    prefix별로 과거 selected 값을 빈도+최신성으로 스코어링한 뒤, Faiss로 찾은
    의미적 인접 키워드를 context로 KeywordGenerator에 전달해 오타/연관 후보를
    보강하고, 최종 목록을 sugg:{prefix}에 원자적으로 쓴다.

    반환값은 prefix별로 실제 Redis에 기록된 suggestions 목록이다 (검증용).
    """
    logger.info("batch started: %d events", len(events))

    grouped = group_events_by_prefix(events)
    if not grouped:
        logger.info("batch skipped: no events to process")
        return {}

    vocabulary = sorted({event.selected for event in events})
    index = build_index(vocabulary, embedding_model)
    save_index_atomic(index, index_path)
    logger.info("faiss index built and saved: %d keywords -> %s", len(vocabulary), index_path)

    written: dict[str, list[str]] = {}
    for prefix, prefix_events in grouped.items():
        logger.info("processing prefix=%r (%d events)", prefix, len(prefix_events))
        try:
            scored = score_keywords(prefix_events, top_n=top_n)
            base_suggestions = [item.keyword for item in scored]

            context = nearest_keywords(
                index, vocabulary, embedding_model, prefix, top_k=context_size
            )
            generated = keyword_generator.generate(prefix, context)

            suggestions = _merge_unique(base_suggestions, generated)[:top_n]
            write_suggestions(redis_client, prefix, suggestions)
            written[prefix] = suggestions
        except Exception:
            logger.exception(
                "failed to process prefix=%r; %d prefixes already written to Redis: %s",
                prefix,
                len(written),
                sorted(written.keys()),
            )
            raise

    logger.info("batch completed: %d prefixes written", len(written))
    return written


def _merge_unique(*keyword_lists: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for keywords in keyword_lists:
        for keyword in keywords:
            if keyword not in seen:
                seen.add(keyword)
                merged.append(keyword)
    return merged
