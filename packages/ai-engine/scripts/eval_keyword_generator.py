"""KeywordGenerator(env var로 설정된 실모델)의 생성 품질을 정성 검수하는 수동 스크립트.

pytest 스위트/커버리지 게이트 밖에 둔다 - 실모델 가중치(E5/Qwen) 다운로드가
전제이므로 CI에서 자동 실행하지 않는다. 사용법은 packages/ai-engine/README.md
"생성 품질 평가" 섹션 참고.

    uv sync --extra models
    export KEYWORD_GENERATOR_PROVIDER=qwen
    export QWEN_MODEL_PATH=/path/to/qwen2.5-1.5b-instruct-q4_k_m.gguf
    uv run python scripts/eval_keyword_generator.py
"""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path

from ai_engine.candidate_filters import load_wordlist
from ai_engine.guarded_keyword_generator import GuardedKeywordGenerator
from ai_engine.runner import build_keyword_generator

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "typo_synonym_pairs.json"
MATCH_SIMILARITY_THRESHOLD = 0.5


def _is_match(correct: str, generated: list[str]) -> bool:
    if correct in generated:
        return True
    return any(
        difflib.SequenceMatcher(None, correct, candidate).ratio() >= MATCH_SIMILARITY_THRESHOLD
        for candidate in generated
    )


def main() -> None:
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    blocklist = load_wordlist(os.environ.get("SUGGESTION_BLOCKLIST_PATH"))
    generator = GuardedKeywordGenerator(build_keyword_generator(), blocklist=blocklist)

    results_by_type: dict[str, list[bool]] = {}

    print(f"평가 대상: {len(fixtures)}개 (context 없이 prefix만 사용 - README 한계 참고)\n")
    for item in fixtures:
        prefix, correct, item_type = item["prefix"], item["correct"], item["type"]
        generated = generator.generate(prefix, [])
        matched = _is_match(correct, generated)
        results_by_type.setdefault(item_type, []).append(matched)

        status = "PASS" if matched else "FAIL"
        print(f"[{status}] prefix={prefix!r} correct={correct!r} generated={generated}")

    print("\n--- 요약 ---")
    total_matched = 0
    total_count = 0
    for item_type, outcomes in sorted(results_by_type.items()):
        matched = sum(outcomes)
        total_matched += matched
        total_count += len(outcomes)
        print(f"{item_type}: {matched}/{len(outcomes)} ({matched / len(outcomes):.0%})")
    print(f"전체: {total_matched}/{total_count} ({total_matched / total_count:.0%})")


if __name__ == "__main__":
    main()
