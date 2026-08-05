from __future__ import annotations

import sys
import types

import pytest

MODULE_PATH = "ai_engine.qwen_keyword_generator"


class _FakeLlama:
    """llama_cpp.Llama의 테스트용 대역.

    호출 인자를 기록해 QwenKeywordGenerator가 model_path/n_ctx를 올바르게
    전달하는지, 프롬프트에 prefix/context가 올바르게 삽입되는지 검증한다.
    """

    def __init__(self, model_path: str, n_ctx: int, seed: int = -1) -> None:
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.seed = seed
        self.calls: list[tuple[str, int, list[str], float]] = []
        self.response_text = "노트북, 랩탑, 맥북"

    def __call__(
        self, prompt: str, max_tokens: int, stop: list[str] | None = None, temperature: float = 0.8
    ) -> dict:
        self.calls.append((prompt, max_tokens, stop, temperature))
        return {"choices": [{"text": self.response_text}]}


@pytest.fixture
def fake_llama_cpp_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    fake_module = types.ModuleType("llama_cpp")
    fake_module.Llama = _FakeLlama  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_module)
    # 이미 임포트된 ai_engine.qwen_keyword_generator이 있다면 제거해, 다음 임포트가
    # 방금 주입한 fake llama_cpp를 지연 임포트하도록 강제한다.
    monkeypatch.delitem(sys.modules, MODULE_PATH, raising=False)
    return fake_module


def test_constructor_passes_model_path_and_n_ctx_to_llama(fake_llama_cpp_module):
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf", n_ctx=256)

    assert generator._llm.model_path == "/models/qwen.gguf"
    assert generator._llm.n_ctx == 256


def test_constructor_uses_default_n_ctx_and_max_tokens_when_unset(fake_llama_cpp_module):
    from ai_engine.qwen_keyword_generator import (
        DEFAULT_QWEN_MAX_TOKENS,
        DEFAULT_QWEN_N_CTX,
        QwenKeywordGenerator,
    )

    generator = QwenKeywordGenerator("/models/qwen.gguf")

    assert generator._llm.n_ctx == DEFAULT_QWEN_N_CTX
    assert generator._max_tokens == DEFAULT_QWEN_MAX_TOKENS
    assert generator._llm.seed == -1


def test_constructor_passes_seed_to_llama_for_reproducible_runs(fake_llama_cpp_module):
    """기본값(-1)은 매번 다른 시드를 써 배치마다 생성 결과가 조금씩 달라진다.
    seed를 명시하면(예: 품질 벤치마크 재현) 같은 입력/모델에서 항상 같은 출력이 나와야
    "이 변경이 실제로 점수를 바꿨는지"를 노이즈와 구별할 수 있다."""
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf", seed=42)

    assert generator._llm.seed == 42


def test_generate_builds_prompt_with_prefix_and_context(fake_llama_cpp_module):
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf", max_tokens=32)
    generator.generate("노트북", ["가성비 노트북", "맥북"])

    prompt, max_tokens, _stop, _temperature = generator._llm.calls[0]
    assert "노트북" in prompt
    assert "가성비 노트북, 맥북" in prompt
    assert max_tokens == 32


def test_generate_stops_at_newline_to_avoid_trailing_commentary(fake_llama_cpp_module):
    """모델이 콤마 목록 뒤에 줄바꿈으로 번역/부연설명을 덧붙이면(예: "노트북\\n번역결과: ...")
    split(",")가 그 덩어리를 통째로 하나의 후보 문자열로 묶어 정답을 오염시킨다
    (packages/ai-engine/scripts/eval_pipeline_quality.py 벤치마크에서 실측된 실패 사례).
    llama.cpp의 stop 파라미터로 첫 줄바꿈에서 생성을 끊어 애초에 이런 오염을 막는다."""
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf")
    generator.generate("노트북", [])

    _prompt, _max_tokens, stop, _temperature = generator._llm.calls[0]
    assert stop == ["\n"]


def test_generate_uses_greedy_decoding_by_default(fake_llama_cpp_module):
    """temperature=0.8(llama.cpp 기본값)은 모델이 context에 정답이 있어도 그걸 그대로
    쓰지 않고 그럴듯한 변형을 창작하는 경우가 있었다(예: "노트북" context가 있는데도
    "노트부"/"카메라상"을 생성 - eval_pipeline_quality.py 벤치마크에서 실측). 오타/유의어
    교정은 창의성보다 context를 그대로 베끼는 게 유리하므로 temperature=0(탐욕적
    디코딩)을 기본값으로 한다. 이 변경만으로 벤치마크의 오타 Hit@5가 90%→95%로 올랐다."""
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf")
    generator.generate("노트북", [])

    _prompt, _max_tokens, _stop, temperature = generator._llm.calls[0]
    assert temperature == 0.0


def test_generate_allows_temperature_override(fake_llama_cpp_module):
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf", temperature=0.8)
    generator.generate("노트북", [])

    _prompt, _max_tokens, _stop, temperature = generator._llm.calls[0]
    assert temperature == 0.8


def test_generate_parses_comma_separated_output_and_strips_whitespace(fake_llama_cpp_module):
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf")
    generator._llm.response_text = " 노트북 ,랩탑,, 맥북"

    result = generator.generate("노트북", [])

    assert result == ["노트북", "랩탑", "맥북"]


def test_generate_returns_empty_list_when_model_output_is_empty(fake_llama_cpp_module):
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf")
    generator._llm.response_text = ""

    assert generator.generate("노트북", []) == []


def test_conforms_to_keyword_generator_protocol(fake_llama_cpp_module):
    from ai_engine.keyword_generator import KeywordGenerator
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf")

    assert isinstance(generator, KeywordGenerator)
