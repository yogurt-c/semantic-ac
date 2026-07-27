# ai-engine (비동기 AI 배치 엔진)

검색 이벤트 로그(트랙 B가 DuckDB `search_events` 테이블에 적재)를 읽어, 빈도+최신성
기반으로 키워드를 스코어링하고, 임베딩/Faiss로 의미적 연관 키워드를 찾아, 오타/문맥
연관 키워드를 보강한 뒤 Redis에 자동완성 사전(`sugg:{prefix}`)을 원자적으로 기록하는
배치 파이프라인이다. 상시 실행 서버가 아니라 스케줄러(APScheduler/cron)로 주기 실행되는
원샷 작업으로 설계되어 있다 (`docs/CONTRACT.md`, `TODO.md` 0번 참조).

## 확정된 기술 스택

- 임베딩 모델: `intfloat/multilingual-e5-small`
- Vector DB: Faiss (라이브러리 내장, 별도 서버 없음)
- sLLM: Llama.cpp + Qwen2.5-1.5B-GGUF (4-bit 양자화)

## 구조

```
src/ai_engine/
  events.py             SearchEvent (search_events 레코드 1건)
  db_reader.py           DuckDB search_events 테이블 읽기 (read-only)
  scoring.py             빈도+최신성 스코어링 순수 함수 (DB 비의존)
  embeddings.py          EmbeddingModel Protocol + E5SmallEmbeddingModel(실제 통합 지점)
  vector_index.py        Faiss 인덱스 빌드 / 원자적 저장(os.replace) / 최근접 검색
  keyword_generator.py   KeywordGenerator Protocol (오타/문맥 연관 키워드 생성)
  redis_writer.py        sugg:{prefix} 원자적 SET (docs/CONTRACT.md 섹션 3)
  pipeline.py            스코어링 -> 임베딩/Faiss -> KeywordGenerator -> Redis 조립
tests/
  conftest.py            FakeEmbeddingModel, FakeKeywordGenerator 등 테스트 더블
  fixtures/typo_synonym_pairs.json   한국어 오타/유의어 평가 샘플 15개
```

## 실행

```bash
uv sync --group dev
uv run pytest          # 전체 테스트 + 커버리지(80%+ 게이트)
```

배치를 실제로 돌리려면 `ai_engine.pipeline.run_batch()`에 실제 구성요소를 주입한다:

```python
from ai_engine.db_reader import fetch_search_events
from ai_engine.pipeline import run_batch

events = fetch_search_events("path/to/search_events.duckdb")
run_batch(events, embedding_model, keyword_generator, redis_client, "path/to/index.faiss")
```

## 다음 단계 (이번 작업 범위 밖)

### 1. multilingual-e5-small 실제 로딩

`E5SmallEmbeddingModel`(`embeddings.py`)은 이미 통합 지점으로 연결되어 있다.
`encode_passages()`/`encode_query()`를 처음 호출하는 시점에 `sentence-transformers`가
지연 임포트되어 모델 가중치(약 470MB)를 다운로드/로드한다. e5 계열 모델은 인덱싱
대상(passage)과 질의(query)에 서로 다른 프리픽스를 붙여야 검색 품질이 보장되므로,
`EmbeddingModel` Protocol도 두 메서드로 역할을 분리해두었다. 필요한 작업은 다음뿐이다:

```bash
uv sync --extra models   # sentence-transformers 설치
```

운영 환경에서는 최초 배치 실행 전에 모델을 미리 캐시해두어(`HF_HOME` 등) 배치
실행 중 네트워크 의존을 없애는 것을 권장한다.

### 2. Llama.cpp + Qwen2.5-1.5B-GGUF 실제 연결

`KeywordGenerator` Protocol만 정의되어 있고 실제 구현체는 없다 (fake만 파이프라인에
조립됨). GGUF 모델 파일(수 GB) 다운로드와 `llama-cpp-python` 추론 연결은 리소스
소모가 크므로, 별도 승인 후 다음과 같은 구현체를 추가하는 형태로 진행한다:

```python
from llama_cpp import Llama

class QwenKeywordGenerator:
    def __init__(self, model_path: str) -> None:
        self._llm = Llama(model_path=model_path, n_ctx=512)

    def generate(self, prefix: str, context: list[str]) -> list[str]:
        prompt = (
            f"다음 검색어와 연관된 오타/유의어 키워드를 콤마로 구분해 나열하라.\n"
            f"검색어: {prefix}\n연관 키워드: {', '.join(context)}\n출력:"
        )
        output = self._llm(prompt, max_tokens=64)
        text = output["choices"][0]["text"]
        return [candidate.strip() for candidate in text.split(",") if candidate.strip()]
```

- 모델: `Qwen2.5-1.5B-Instruct-GGUF` (Q4_K_M 등 4-bit 양자화 버전)
- 설치: `uv sync --extra models` (`llama-cpp-python` 포함)
- 실제 다운로드/추론 연결 시 `tests/fixtures/typo_synonym_pairs.json`을 활용해
  생성 품질 정성 검수를 진행할 것 (이번 범위에서는 구조적 유효성만 검증함).

### 3. 통합/운영

- `docker-compose.yml`에 AI Worker 서비스로 편입 (`TODO.md` 3번)
- 스케줄러(APScheduler/cron)로 주기 실행 연결
- 저사양 CPU/RAM 환경에서 4-bit 양자화 모델 구동 스트레스 테스트
