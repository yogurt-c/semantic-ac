"""baseline(HashingEmbeddingModel/NoopKeywordGenerator) vs 실모델(E5/Qwen) 두 설정으로
run_batch 전체 파이프라인(scoring -> co-occurrence -> Faiss -> KeywordGenerator)을 돌려
오타/유의어 교정 Hit@5를 비교하고 막대그래프로 저장하는 수동 스크립트.

eval_keyword_generator.py는 KeywordGenerator 하나만 context 없이 평가해 "실제 배치보다
보수적인" 수치가 나온다는 한계가 있다(README.md "생성 품질 평가" 참고). 이 스크립트는
그 한계를 메우기 위해 각 테스트 prefix를 실제로 한 번 검색한 것처럼 이벤트를 주입하고
run_batch를 그대로 실행해, `/suggest`가 실제로 반환할 값 그대로를 채점한다.

각 테스트 prefix마다 "누군가 그 오타/유의어로 검색해봤다"는 최소 이벤트 1건만 주입한다
(selected=prefix 자기 자신 - scoring 레이어가 정답을 우연히 알려주지 않도록). 정답
자체는 별도의 "정상 표기로 검색해 정상 표기를 골랐다" 이벤트로 vocabulary에 심어
Faiss가 찾을 수 있게 한다. baseline은 이 vocabulary를 의미적으로 활용할 방법이 없으므로
(HashingEmbeddingModel은 의미 없는 해시 벡터, NoopKeywordGenerator는 항상 빈 리스트)
구조적으로 0%에 가깝게 나오는 것이 기대값이다 - README 인트로의 "Trie 기반은 오타/유의어를
처리 못한다"는 주장을 이 스크립트가 직접 증명한다.

pytest 스위트/커버리지 게이트 밖에 둔다 - 실모델 가중치(E5/Qwen) 다운로드와 matplotlib이
전제이므로 CI에서 자동 실행하지 않는다. 사용법은 packages/ai-engine/README.md
"파이프라인 품질 벤치마크" 섹션 참고.

    uv sync --extra models
    export QWEN_MODEL_PATH=/path/to/qwen2.5-1.5b-instruct-q4_k_m.gguf
    uv run --with matplotlib python scripts/eval_pipeline_quality.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import fakeredis

from ai_engine.embeddings import DEFAULT_E5_MODEL_NAME, E5SmallEmbeddingModel
from ai_engine.events import SearchEvent
from ai_engine.pipeline import run_batch
from ai_engine.qwen_keyword_generator import DEFAULT_QWEN_N_CTX, QwenKeywordGenerator
from ai_engine.stub_components import HashingEmbeddingModel, NoopKeywordGenerator

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "pipeline_quality_benchmark.json"
)
CHART_PATH = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "assets" / "pipeline-quality-benchmark.png"
TOP_K = 5
TYPES = ["typo", "synonym"]


def _build_events(pairs: list[dict]) -> list[SearchEvent]:
    now = datetime.now(timezone.utc)
    vocabulary_terms = sorted({pair["correct"] for pair in pairs})
    events = [
        SearchEvent(prefix=term, selected=term, action="final_search", event_ts=now)
        for term in vocabulary_terms
    ]
    events += [
        SearchEvent(prefix=pair["prefix"], selected=pair["prefix"], action="final_search", event_ts=now)
        for pair in pairs
    ]
    return events


def _hit_rates(written: dict[str, list[str]], pairs: list[dict]) -> dict[str, float]:
    rates: dict[str, float] = {}
    for item_type in TYPES:
        subset = [pair for pair in pairs if pair["type"] == item_type]
        hits = sum(
            1 for pair in subset if pair["correct"] in written.get(pair["prefix"], [])[:TOP_K]
        )
        rates[item_type] = hits / len(subset)
    return rates


def _run_config(embedding_model, keyword_generator, pairs: list[dict]) -> dict[str, float]:
    events = _build_events(pairs)
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    with TemporaryDirectory() as tmp_dir:
        written = run_batch(
            events, embedding_model, keyword_generator, redis_client, Path(tmp_dir) / "eval.faiss"
        )
    return _hit_rates(written, pairs)


_KOREAN_FONT_CANDIDATES = [
    "AppleGothic",
    "Apple SD Gothic Neo",
    "Noto Sans CJK KR",
    "Noto Sans KR",
    "Malgun Gothic",
    "NanumGothic",
]


def _use_korean_font() -> None:
    """DejaVu Sans(matplotlib 기본 폰트)는 한글 glyph가 없어 라벨이 네모로 깨진다.
    OS에 설치된 한글 폰트 중 matplotlib가 이미 찾은 것을 우선순위대로 골라 쓴다."""
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt

    available = {f.name for f in fm.fontManager.ttflist}
    for candidate in _KOREAN_FONT_CANDIDATES:
        if candidate in available:
            plt.rcParams["font.family"] = candidate
            plt.rcParams["axes.unicode_minus"] = False
            return
    print("경고: 한글 지원 폰트를 찾지 못했다 - 차트 라벨이 깨질 수 있음")


def _save_chart(results: dict[str, dict[str, float]]) -> None:
    import matplotlib.pyplot as plt

    _use_korean_font()
    labels = {"typo": "오타 교정", "synonym": "유의어"}
    configs = list(results.keys())
    x = range(len(TYPES))
    width = 0.35

    fig, ax = plt.subplots(figsize=(6, 4))
    for i, config in enumerate(configs):
        offsets = [pos + (i - 0.5) * width for pos in x]
        values = [results[config][item_type] * 100 for item_type in TYPES]
        bars = ax.bar(offsets, values, width, label=config)
        ax.bar_label(bars, fmt="%.0f%%")

    ax.set_xticks(list(x))
    ax.set_xticklabels([labels[item_type] for item_type in TYPES])
    ax.set_ylabel(f"Hit@{TOP_K} (%)")
    ax.set_ylim(0, 110)
    ax.set_title("baseline(hashing/noop) vs 실모델(E5/Qwen) 정확도 비교")
    ax.legend()
    fig.tight_layout()

    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(CHART_PATH, dpi=150)
    print(f"\n차트 저장: {CHART_PATH}")


def main() -> None:
    pairs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    print(f"평가 대상: {len(pairs)}개 (typo {sum(1 for p in pairs if p['type'] == 'typo')} / "
          f"synonym {sum(1 for p in pairs if p['type'] == 'synonym')})\n")

    results: dict[str, dict[str, float]] = {}

    print("[1/2] baseline(hashing/noop) 실행 중...")
    results["baseline"] = _run_config(HashingEmbeddingModel(), NoopKeywordGenerator(), pairs)

    print("[2/2] 실모델(E5/Qwen) 실행 중... (최초 실행 시 E5 다운로드로 시간이 걸릴 수 있음)")
    model_path = os.environ["QWEN_MODEL_PATH"]
    e5 = E5SmallEmbeddingModel(os.environ.get("E5_MODEL_NAME", DEFAULT_E5_MODEL_NAME))
    qwen = QwenKeywordGenerator(model_path, n_ctx=int(os.environ.get("QWEN_N_CTX", DEFAULT_QWEN_N_CTX)))
    results["e5+qwen"] = _run_config(e5, qwen, pairs)

    print("\n--- 결과 (Hit@5) ---")
    for config, rates in results.items():
        for item_type in TYPES:
            print(f"{config:>10} / {item_type:<8}: {rates[item_type]:.0%}")

    _save_chart(results)


if __name__ == "__main__":
    main()
