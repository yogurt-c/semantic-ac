"""전통적인 편집거리(Levenshtein) 기반 스펠체크 vs semantic-ac(E5+Qwen, 임베딩 크기별)를
같은 오타/유의어 fixture로 비교해 Hit@5 막대그래프로 저장하는 수동 스크립트.

처음에는 이 프로젝트 자체의 placeholder(HashingEmbeddingModel/NoopKeywordGenerator)를
baseline으로 삼았으나, NoopKeywordGenerator는 애초에 항상 빈 리스트를 반환하도록
만들어진 구조 검증용 stub이라 "0%"가 나오는 게 실행해보지 않아도 이미 알 수 있는
당연한 결과(tautology)였다 - 허수아비와 비교하는 셈이라 설득력이 없다. 그래서
baseline을 실제로 많은 시스템이 쓰는 비-ML 기법인 편집거리 기반 스펠체크로 바꿨다.

fixture의 유의어를 prefix/correct가 문자열을 전혀 공유하지 않는 "진짜" 유의어로
다시 짠 뒤 측정해보니, 기본 모델(multilingual-e5-small)은 유의어에서 Levenshtein과
거의 다를 바 없이 낮은 점수가 나왔다 - 원인을 진단해보니 Qwen 생성 문제가 아니라
Faiss/E5 검색 단계에서부터 진짜 정답이 top-5 context에 거의 안 들어오는 것이었다.
그래서 E5_MODEL_SWEEP으로 e5-small/base/large 세 크기를 전부 돌려, "임베딩 모델
크기가 커질수록 유의어 검색 품질이 실제로 좋아지는가"까지 같은 그래프에 담는다 -
이 프로젝트가 강조하는 "리소스 대비 품질 트레이드오프"를 직접 보여주는 숫자다.

eval_keyword_generator.py는 KeywordGenerator 하나만 context 없이 평가해 "실제 배치보다
보수적인" 수치가 나온다는 한계가 있다(README.md "생성 품질 평가" 참고). semantic-ac
쪽 수치는 이 스크립트가 실제 run_batch 전체(scoring -> co-occurrence -> Faiss ->
KeywordGenerator)를 그대로 실행해서 낸다 - `/suggest`가 실제로 반환할 값 그대로를
채점한다. 각 테스트 prefix마다 "누군가 그 오타/유의어로 검색해봤다"는 최소 이벤트
1건만 주입한다(selected=prefix 자기 자신 - scoring 레이어가 정답을 우연히 알려주지
않도록). 정답 자체는 별도의 "정상 표기로 검색해 정상 표기를 골랐다" 이벤트로
vocabulary에 심어 Faiss가 찾을 수 있게 한다.

pytest 스위트/커버리지 게이트 밖에 둔다 - 실모델 가중치(E5/Qwen) 다운로드와 matplotlib이
전제이므로 CI에서 자동 실행하지 않는다. e5-large까지 받으면 다운로드만 3GB 안팎이라
로컬 디스크 여유를 확인할 것. 사용법은 packages/ai-engine/README.md
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

from ai_engine.embeddings import E5SmallEmbeddingModel
from ai_engine.events import SearchEvent
from ai_engine.pipeline import run_batch
from ai_engine.qwen_keyword_generator import DEFAULT_QWEN_N_CTX, QwenKeywordGenerator

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "pipeline_quality_benchmark.json"
)
CHART_PATH = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "assets" / "pipeline-quality-benchmark.png"
TOP_K = 5
TYPES = ["typo", "synonym"]
E5_MODEL_SWEEP = [
    ("e5-small+qwen", "intfloat/multilingual-e5-small", "e5-small+Qwen (~470MB)"),
    ("e5-base+qwen", "intfloat/multilingual-e5-base", "e5-base+Qwen (~1.1GB)"),
    ("e5-large+qwen", "intfloat/multilingual-e5-large", "e5-large+Qwen (~2.2GB)"),
]
CONFIG_LABELS = {"levenshtein": "Levenshtein 편집거리", **{key: label for key, _, label in E5_MODEL_SWEEP}}


def _levenshtein_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous_row = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current_row = [i]
        for j, char_b in enumerate(b, start=1):
            insert_cost = current_row[j - 1] + 1
            delete_cost = previous_row[j] + 1
            substitute_cost = previous_row[j - 1] + (char_a != char_b)
            current_row.append(min(insert_cost, delete_cost, substitute_cost))
        previous_row = current_row
    return previous_row[-1]


def _run_levenshtein_baseline(pairs: list[dict]) -> dict[str, float]:
    """semantic-ac 쪽(_build_events)과 동일한 후보 풀(정답 + 테스트 prefix 자기 자신)에서
    찾게 해 두 방식이 같은 vocabulary를 놓고 경쟁하도록 맞춘다 - vocabulary 크기가
    다르면 편집거리 top-K가 우연히 맞을 확률 자체가 달라져 비교가 불공정해진다."""
    vocabulary = sorted({pair["correct"] for pair in pairs} | {pair["prefix"] for pair in pairs})
    rates: dict[str, float] = {}
    for item_type in TYPES:
        subset = [pair for pair in pairs if pair["type"] == item_type]
        hits = 0
        for pair in subset:
            ranked = sorted(vocabulary, key=lambda term: _levenshtein_distance(pair["prefix"], term))
            if pair["correct"] in ranked[:TOP_K]:
                hits += 1
        rates[item_type] = hits / len(subset)
    return rates


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


def _run_semantic_ac(embedding_model, keyword_generator, pairs: list[dict]) -> dict[str, float]:
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
    type_labels = {"typo": "오타 교정", "synonym": "유의어"}
    configs = list(results.keys())
    n = len(configs)
    x = range(len(TYPES))
    width = 0.8 / n

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, config in enumerate(configs):
        offsets = [pos + (i - (n - 1) / 2) * width for pos in x]
        values = [results[config][item_type] * 100 for item_type in TYPES]
        bars = ax.bar(offsets, values, width, label=CONFIG_LABELS.get(config, config))
        ax.bar_label(bars, fmt="%.0f%%", fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels([type_labels[item_type] for item_type in TYPES])
    ax.set_ylabel(f"Hit@{TOP_K} (%)")
    ax.set_ylim(0, 110)
    ax.set_title("Levenshtein 편집거리 vs semantic-ac(임베딩 크기별) 정확도 비교")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2)
    fig.tight_layout()

    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(CHART_PATH, dpi=150)
    print(f"\n차트 저장: {CHART_PATH}")


def main() -> None:
    pairs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    print(f"평가 대상: {len(pairs)}개 (typo {sum(1 for p in pairs if p['type'] == 'typo')} / "
          f"synonym {sum(1 for p in pairs if p['type'] == 'synonym')})\n")

    results: dict[str, dict[str, float]] = {}

    print("[1/{}] Levenshtein 편집거리 baseline 실행 중...".format(len(E5_MODEL_SWEEP) + 1))
    results["levenshtein"] = _run_levenshtein_baseline(pairs)

    model_path = os.environ["QWEN_MODEL_PATH"]
    qwen = QwenKeywordGenerator(model_path, n_ctx=int(os.environ.get("QWEN_N_CTX", DEFAULT_QWEN_N_CTX)))
    for step, (config_key, model_name, label) in enumerate(E5_MODEL_SWEEP, start=2):
        print(f"[{step}/{len(E5_MODEL_SWEEP) + 1}] {label} 실행 중... "
              "(최초 실행 시 모델 다운로드로 시간이 걸릴 수 있음)")
        e5 = E5SmallEmbeddingModel(model_name)
        results[config_key] = _run_semantic_ac(e5, qwen, pairs)

    print("\n--- 결과 (Hit@5) ---")
    for config, rates in results.items():
        for item_type in TYPES:
            print(f"{CONFIG_LABELS[config]:>24} / {item_type:<8}: {rates[item_type]:.0%}")

    _save_chart(results)


if __name__ == "__main__":
    main()
