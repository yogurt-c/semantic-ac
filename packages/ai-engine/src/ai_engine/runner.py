from __future__ import annotations

import argparse
import logging
import os
import time

import redis

from ai_engine.candidate_filters import DEFAULT_MAX_LENGTH, DEFAULT_MIN_LENGTH, load_wordlist
from ai_engine.db_reader import fetch_search_events
from ai_engine.embeddings import DEFAULT_E5_MODEL_NAME, E5SmallEmbeddingModel, EmbeddingModel
from ai_engine.keyword_generator import KeywordGenerator
from ai_engine.pipeline import (
    DEFAULT_CONTEXT_SIZE,
    DEFAULT_COOCCURRENCE_HALF_LIFE_HOURS,
    DEFAULT_COOCCURRENCE_SEED_SIZE,
    DEFAULT_GENERATED_MAX_SHARE,
    DEFAULT_MIN_OCCURRENCES,
    DEFAULT_TOP_N,
    run_batch,
)
from ai_engine.qwen_keyword_generator import (
    DEFAULT_QWEN_MAX_TOKENS,
    DEFAULT_QWEN_N_CTX,
    QwenKeywordGenerator,
)
from ai_engine.stub_components import HashingEmbeddingModel, NoopKeywordGenerator

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_DUCKDB_PATH = "data/search_events.duckdb"
DEFAULT_INDEX_PATH = "data/index.faiss"


def build_embedding_model() -> EmbeddingModel:
    """EMBEDDING_PROVIDER env var로 임베딩 모델을 선택한다 (hashing(기본) | e5)."""
    provider = os.environ.get("EMBEDDING_PROVIDER", "hashing")
    if provider == "hashing":
        return HashingEmbeddingModel()
    if provider == "e5":
        model_name = os.environ.get("E5_MODEL_NAME", DEFAULT_E5_MODEL_NAME)
        return E5SmallEmbeddingModel(model_name)
    raise ValueError(f"unknown EMBEDDING_PROVIDER: {provider!r}")


def build_keyword_generator() -> KeywordGenerator:
    """KEYWORD_GENERATOR_PROVIDER env var로 키워드 생성기를 선택한다 (noop(기본) | qwen)."""
    provider = os.environ.get("KEYWORD_GENERATOR_PROVIDER", "noop")
    if provider == "noop":
        return NoopKeywordGenerator()
    if provider == "qwen":
        model_path = os.environ["QWEN_MODEL_PATH"]
        n_ctx = int(os.environ.get("QWEN_N_CTX", DEFAULT_QWEN_N_CTX))
        max_tokens = int(os.environ.get("QWEN_MAX_TOKENS", DEFAULT_QWEN_MAX_TOKENS))
        use_chat_template = os.environ.get("QWEN_USE_CHAT_TEMPLATE", "false").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        return QwenKeywordGenerator(
            model_path, n_ctx=n_ctx, max_tokens=max_tokens, use_chat_template=use_chat_template
        )
    raise ValueError(f"unknown KEYWORD_GENERATOR_PROVIDER: {provider!r}")


def run_once(
    redis_url: str,
    duckdb_path: str,
    index_path: str,
    *,
    embedding_model: EmbeddingModel | None = None,
    keyword_generator: KeywordGenerator | None = None,
    top_n: int = DEFAULT_TOP_N,
    context_size: int = DEFAULT_CONTEXT_SIZE,
    cooccurrence_half_life_hours: float = DEFAULT_COOCCURRENCE_HALF_LIFE_HOURS,
    cooccurrence_seed_size: int = DEFAULT_COOCCURRENCE_SEED_SIZE,
    min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
    min_length: int = DEFAULT_MIN_LENGTH,
    max_length: int = DEFAULT_MAX_LENGTH,
    blocklist: frozenset[str] = frozenset(),
    generated_max_share: float = DEFAULT_GENERATED_MAX_SHARE,
) -> dict[str, list[str]]:
    """search_events를 읽어 배치 1회를 실행한다.

    embedding_model/keyword_generator를 넘기지 않으면 HashingEmbeddingModel/
    NoopKeywordGenerator placeholder로 파이프라인 구조만 검증한다
    (stub_components.py 참고). 실모델(E5/Qwen)을 넘겨도 run_batch가 항상
    GuardedKeywordGenerator로 감싸기 때문에 정제 가드레일은 그대로 적용된다.
    """
    events = fetch_search_events(duckdb_path)
    if not events:
        logger.info("no search events found at %s; skipping batch", duckdb_path)
        return {}

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    return run_batch(
        events,
        embedding_model or HashingEmbeddingModel(),
        keyword_generator or NoopKeywordGenerator(),
        client,
        index_path,
        top_n=top_n,
        context_size=context_size,
        cooccurrence_half_life_hours=cooccurrence_half_life_hours,
        cooccurrence_seed_size=cooccurrence_seed_size,
        min_occurrences=min_occurrences,
        min_length=min_length,
        max_length=max_length,
        blocklist=blocklist,
        generated_max_share=generated_max_share,
    )


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="ai-engine 배치 러너 (스케줄러 대체용 원샷/반복 실행)")
    parser.add_argument(
        "--once", action="store_true", help="배치를 1회만 실행하고 종료한다 (실패 시 예외를 그대로 전파)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("BATCH_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)),
        help="반복 실행 주기(초). --once와 함께 쓰지 않음",
    )
    args = parser.parse_args(argv)

    redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
    duckdb_path = os.environ.get("DUCKDB_PATH", DEFAULT_DUCKDB_PATH)
    index_path = os.environ.get("INDEX_PATH", DEFAULT_INDEX_PATH)
    top_n = int(os.environ.get("SUGGESTION_TOP_N", DEFAULT_TOP_N))
    context_size = int(os.environ.get("FAISS_CONTEXT_SIZE", DEFAULT_CONTEXT_SIZE))
    cooccurrence_half_life_hours = float(
        os.environ.get("COOCCURRENCE_HALF_LIFE_HOURS", DEFAULT_COOCCURRENCE_HALF_LIFE_HOURS)
    )
    cooccurrence_seed_size = int(
        os.environ.get("COOCCURRENCE_SEED_SIZE", DEFAULT_COOCCURRENCE_SEED_SIZE)
    )
    min_occurrences = int(os.environ.get("SUGGESTION_MIN_COUNT", DEFAULT_MIN_OCCURRENCES))
    min_length = int(os.environ.get("SUGGESTION_MIN_LEN", DEFAULT_MIN_LENGTH))
    max_length = int(os.environ.get("SUGGESTION_MAX_LEN", DEFAULT_MAX_LENGTH))
    generated_max_share = float(
        os.environ.get("SUGGESTION_GENERATED_MAX_SHARE", DEFAULT_GENERATED_MAX_SHARE)
    )
    blocklist = load_wordlist(os.environ.get("SUGGESTION_BLOCKLIST_PATH"))

    # 배치 루프 진입 전 1회만 생성 — 매 주기 GGUF/E5 가중치를 다시 로드하지 않기
    # 위함이다. QWEN_MODEL_PATH 누락 등 설정 오류는 위 env var 파싱과 동일하게
    # 여기서 즉시 실패해 운영자가 바로 알아챌 수 있게 한다.
    embedding_model = build_embedding_model()
    keyword_generator = build_keyword_generator()

    def _run_once() -> dict[str, list[str]]:
        return run_once(
            redis_url,
            duckdb_path,
            index_path,
            embedding_model=embedding_model,
            keyword_generator=keyword_generator,
            top_n=top_n,
            context_size=context_size,
            cooccurrence_half_life_hours=cooccurrence_half_life_hours,
            cooccurrence_seed_size=cooccurrence_seed_size,
            min_occurrences=min_occurrences,
            min_length=min_length,
            max_length=max_length,
            blocklist=blocklist,
            generated_max_share=generated_max_share,
        )

    if args.once:
        _run_once()
        return

    # 상시 실행 루프. search_events 테이블이 아직 없거나(트랙 B 첫 요청 전) 배치 1회가
    # 실패해도 워커 프로세스를 죽이지 않고 다음 주기에 재시도한다 (스케줄러 대체 MVP).
    while True:
        try:
            _run_once()
        except Exception:
            logger.exception("batch cycle failed; will retry next cycle")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
