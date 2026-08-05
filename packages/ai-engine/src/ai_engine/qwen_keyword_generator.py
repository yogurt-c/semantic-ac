from __future__ import annotations

DEFAULT_QWEN_N_CTX = 512
DEFAULT_QWEN_MAX_TOKENS = 64


class QwenKeywordGenerator:
    """Llama.cpp + Qwen2.5-1.5B-GGUF 실제 통합 지점 (KeywordGenerator Protocol 구현체).

    GGUF 가중치(수 GB)를 생성 시점에 지연 임포트하고, 생성자 호출 시 즉시 로드한다
    (runner.main()이 배치 루프 시작 전 1회만 생성 — E5와 달리 llama.cpp는 로드 자체가
    무거워 매 요청 지연 로딩할 이유가 없다). context는 지시문이 아니라 순수 참고
    데이터로만 프롬프트에 들어간다 (사용자 selected 원문이 섞여 들어오므로 프롬프트
    인젝션 표면을 최소화하기 위함).
    """

    def __init__(
        self,
        model_path: str,
        *,
        n_ctx: int = DEFAULT_QWEN_N_CTX,
        max_tokens: int = DEFAULT_QWEN_MAX_TOKENS,
    ) -> None:
        from llama_cpp import Llama

        self._llm = Llama(model_path=model_path, n_ctx=n_ctx)
        self._max_tokens = max_tokens

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        prompt = (
            "다음 검색어와 연관된 오타/유의어 키워드를 콤마로 구분해 나열하라.\n"
            f"검색어: {prefix}\n연관 키워드: {', '.join(context)}\n출력:"
        )
        output = self._llm(prompt, max_tokens=self._max_tokens)
        text = output["choices"][0]["text"]
        return [candidate.strip() for candidate in text.split(",") if candidate.strip()]
