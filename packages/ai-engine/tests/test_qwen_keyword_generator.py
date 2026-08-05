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

    def __init__(self, model_path: str, n_ctx: int) -> None:
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.calls: list[tuple[str, int]] = []
        self.response_text = "노트북, 랩탑, 맥북"

    def __call__(self, prompt: str, max_tokens: int) -> dict:
        self.calls.append((prompt, max_tokens))
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


def test_generate_builds_prompt_with_prefix_and_context(fake_llama_cpp_module):
    from ai_engine.qwen_keyword_generator import QwenKeywordGenerator

    generator = QwenKeywordGenerator("/models/qwen.gguf", max_tokens=32)
    generator.generate("노트북", ["가성비 노트북", "맥북"])

    prompt, max_tokens = generator._llm.calls[0]
    assert "노트북" in prompt
    assert "가성비 노트북, 맥북" in prompt
    assert max_tokens == 32


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
