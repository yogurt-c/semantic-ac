from __future__ import annotations

import argparse
import logging
import os
import time

import redis

from ai_engine.db_reader import fetch_search_events
from ai_engine.pipeline import (
    DEFAULT_CONTEXT_SIZE,
    DEFAULT_COOCCURRENCE_HALF_LIFE_HOURS,
    DEFAULT_COOCCURRENCE_SEED_SIZE,
    DEFAULT_TOP_N,
    run_batch,
)
from ai_engine.stub_components import HashingEmbeddingModel, NoopKeywordGenerator

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_DUCKDB_PATH = "data/search_events.duckdb"
DEFAULT_INDEX_PATH = "data/index.faiss"


def run_once(
    redis_url: str,
    duckdb_path: str,
    index_path: str,
    *,
    top_n: int = DEFAULT_TOP_N,
    context_size: int = DEFAULT_CONTEXT_SIZE,
    cooccurrence_half_life_hours: float = DEFAULT_COOCCURRENCE_HALF_LIFE_HOURS,
    cooccurrence_seed_size: int = DEFAULT_COOCCURRENCE_SEED_SIZE,
) -> dict[str, list[str]]:
    """search_events를 읽어 배치 1회를 실행한다.

    실모델(E5/Qwen) 연결 전까지는 HashingEmbeddingModel/NoopKeywordGenerator
    placeholder로 파이프라인 구조만 검증한다 (stub_components.py 참고).
    """
    events = fetch_search_events(duckdb_path)
    if not events:
        logger.info("no search events found at %s; skipping batch", duckdb_path)
        return {}

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    return run_batch(
        events,
        HashingEmbeddingModel(),
        NoopKeywordGenerator(),
        client,
        index_path,
        top_n=top_n,
        context_size=context_size,
        cooccurrence_half_life_hours=cooccurrence_half_life_hours,
        cooccurrence_seed_size=cooccurrence_seed_size,
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

    def _run_once() -> dict[str, list[str]]:
        return run_once(
            redis_url,
            duckdb_path,
            index_path,
            top_n=top_n,
            context_size=context_size,
            cooccurrence_half_life_hours=cooccurrence_half_life_hours,
            cooccurrence_seed_size=cooccurrence_seed_size,
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
