from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class KeywordGenerator(Protocol):
    """오타/문맥 연관 키워드 Key-Value 사전을 생성하는 인터페이스.

    실제 구현은 Llama.cpp + Qwen2.5-1.5B-GGUF(4bit)로 연결한다. GGUF 모델
    다운로드(수 GB)와 llama-cpp-python 실추론 연결은 이번 작업 범위 밖이며
    README.md의 "다음 단계"에 연결 방법을 문서화했다. 현재는 fake 구현체만
    파이프라인에 조립되어 있다.
    """

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        """prefix와 의미적으로 연관된 context 키워드를 참고해 오타/유의어 후보
        목록을 반환한다. 반환 타입은 list[str] (빈 배열 여부는 구현체 재량)."""
        ...
