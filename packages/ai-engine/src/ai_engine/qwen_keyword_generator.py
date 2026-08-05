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
        seed: int = -1,
        temperature: float = 0.0,
        use_chat_template: bool = False,
    ) -> None:
        from llama_cpp import Llama

        # 기본값(-1)은 매 프로세스마다 다른 시드를 써 생성 결과가 조금씩 달라진다 -
        # 프로덕션 배치에서는 문제 없지만, 품질 벤치마크(scripts/eval_pipeline_quality.py)처럼
        # "이 변경이 실제로 점수를 바꿨는지"를 노이즈와 구별해야 할 때는 고정 시드가 필요하다.
        #
        # use_chat_template=False(기본)일 때는 지금까지 벤치마크로 검증해온 아래
        # 손수 짠 프롬프트+raw completion 경로를 그대로 쓴다 - Qwen2.5 GGUF에 대해
        # 이미 검증된 수치(README.md "파이프라인 품질 벤치마크" 참고)를 조용히
        # 바꾸지 않기 위함이다. Qwen이 아닌 다른 GGUF로 바꿀 때는 use_chat_template=True로
        # 켜면 GGUF에 내장된 chat_template(jinja2 메타데이터)을 llama-cpp-python이
        # 자동 인식해 그 모델의 instruct 포맷에 맞는 프롬프트를 대신 만들어준다 - Ollama/
        # vLLM 등이 쓰는 것과 같은 방식이다. 다만 모든 GGUF가 유효한 template을
        # 내장하고 있는 건 아니므로, 켠 뒤에는 항상 eval 스크립트로 재검증할 것.
        chat_format = "auto" if use_chat_template else None
        self._llm = Llama(model_path=model_path, n_ctx=n_ctx, seed=seed, chat_format=chat_format)
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._use_chat_template = use_chat_template

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        if self._use_chat_template:
            text = self._generate_via_chat_template(prefix, context)
        else:
            text = self._generate_via_legacy_prompt(prefix, context)
        return [candidate.strip() for candidate in text.split(",") if candidate.strip()]

    def _generate_via_legacy_prompt(self, prefix: str, context: list[str]) -> str:
        prompt = (
            "다음 검색어와 연관된 오타/유의어 키워드를 콤마로 구분해 나열하라.\n"
            f"검색어: {prefix}\n연관 키워드: {', '.join(context)}\n출력:"
        )
        # stop=["\n"]으로 콤마 목록 한 줄만 받는다. 이게 없으면 모델이 목록 뒤에
        # 줄바꿈으로 번역/부연설명을 덧붙이는 경우가 있는데(예: "노트북\n번역결과: ..."),
        # split(",")가 그 덩어리를 통째로 한 후보로 묶어 정답 문자열을 오염시킨다
        # (scripts/eval_pipeline_quality.py 벤치마크에서 실측된 실패 사례).
        #
        # temperature 기본값 0(탐욕적 디코딩): llama.cpp 기본값(0.8)에서는 context에
        # 정답이 있어도 모델이 그걸 그대로 쓰지 않고 그럴듯한 변형을 창작하는 경우가
        # 있었다(예: "노트북"이 context에 있는데 "노트부"/"카메라상"을 생성). 오타/유의어
        # 교정은 창의성보다 context를 그대로 베끼는 게 유리해 벤치마크의 오타 Hit@5가
        # 이 변경만으로 90%→95%로 올랐다.
        output = self._llm(
            prompt, max_tokens=self._max_tokens, stop=["\n"], temperature=self._temperature
        )
        return output["choices"][0]["text"]

    def _generate_via_chat_template(self, prefix: str, context: list[str]) -> str:
        # context는 사용자 selected 원문이 섞여 들어오므로 지시문이 아니라 참고
        # 데이터로만 취급해야 프롬프트 인젝션 표면이 최소화된다 - system 메시지에
        # 규칙을 고정하고, context는 user 메시지 안에 데이터로만 넣는다.
        messages = [
            {
                "role": "system",
                "content": "다음 검색어와 연관된 오타/유의어 키워드를 콤마로 구분해 나열하라. "
                "콤마로 구분된 목록 한 줄만 출력하고 다른 설명은 덧붙이지 마라.",
            },
            {
                "role": "user",
                "content": f"검색어: {prefix}\n연관 키워드: {', '.join(context)}",
            },
        ]
        output = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=self._max_tokens,
            stop=["\n"],
            temperature=self._temperature,
        )
        return output["choices"][0]["message"]["content"]
