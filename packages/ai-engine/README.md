# ai-engine

비동기 AI 배치 엔진. [`search-server`](../server)가 DuckDB `search_events` 테이블에
적재한 검색 로그를 읽어, 빈도+최신성 기반으로 키워드를 스코어링하고, 임베딩/Faiss로
의미적 연관 키워드를 찾아, 오타/문맥 연관 키워드를 보강한 뒤 Redis에 자동완성
사전(`sugg:{prefix}`)을 원자적으로 기록하는 배치 파이프라인이다. 상시 실행 서버가
아니라 주기 실행되는 원샷 작업으로 설계되어 있다 (스키마는
[`../../docs/CONTRACT.md`](../../docs/CONTRACT.md) 참고).

## 기술 스택

- 임베딩 모델: `intfloat/multilingual-e5-small`
- Vector DB: Faiss (라이브러리 내장, 별도 서버 프로세스 없음)
- sLLM: Llama.cpp + Qwen2.5-1.5B-GGUF (4-bit 양자화) — 연결 방법은 아래 [로드맵](#로드맵) 참고

## Structure

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
  stub_components.py     HashingEmbeddingModel/NoopKeywordGenerator — 실모델 연결
                         전 docker-compose 기본값 placeholder (실제 추천 품질 없음)
  runner.py              env var(REDIS_URL/DUCKDB_PATH/INDEX_PATH/BATCH_INTERVAL_SECONDS)
                         기반 배치 실행 진입점. `--once`(1회 실행, 예외 전파) /
                         기본(반복 실행, 예외 로깅 후 다음 주기 재시도) 두 모드 지원
tests/
  conftest.py            FakeEmbeddingModel, FakeKeywordGenerator 등 테스트 더블
  fixtures/typo_synonym_pairs.json   한국어 오타/유의어 평가 샘플 15개
```

## 실행

```bash
uv sync --group dev
uv run pytest          # 전체 테스트 + 커버리지(80%+ 게이트)
```

배치를 직접 돌리려면 `ai_engine.pipeline.run_batch()`에 구성요소를 주입한다:

```python
from ai_engine.db_reader import fetch_search_events
from ai_engine.pipeline import run_batch

events = fetch_search_events("path/to/search_events.duckdb")
run_batch(events, embedding_model, keyword_generator, redis_client, "path/to/index.faiss")
```

docker-compose 환경에서는 `runner.py`가 기본값으로 `stub_components`의
placeholder(`HashingEmbeddingModel`, `NoopKeywordGenerator`)를 주입해 파이프라인
구조만 검증한다. 실제 임베딩/sLLM 모델을 연결하려면 아래 로드맵을 참고한다.

## 로드맵

`EmbeddingModel`/`KeywordGenerator`는 둘 다 Protocol로 정의된 통합 지점이라, 아래
구현체로 교체하는 것만으로 실모델을 연결할 수 있다.

### multilingual-e5-small 연결

`E5SmallEmbeddingModel`(`embeddings.py`)은 이미 구현되어 있다.
`encode_passages()`/`encode_query()`를 처음 호출하는 시점에 `sentence-transformers`가
지연 임포트되어 모델 가중치(약 470MB)를 다운로드/로드한다. e5 계열 모델은 인덱싱
대상(passage)과 질의(query)에 서로 다른 프리픽스를 붙여야 검색 품질이 보장되므로,
`EmbeddingModel` Protocol도 두 메서드로 역할을 분리해두었다.

```bash
uv sync --extra models   # sentence-transformers 설치
```

운영 환경에서는 최초 배치 실행 전에 모델을 미리 캐시해두어(`HF_HOME` 등) 배치
실행 중 네트워크 의존을 없애는 것을 권장한다.

### Llama.cpp + Qwen2.5-1.5B-GGUF 연결

`KeywordGenerator` Protocol만 정의되어 있고, 리소스 소모가 큰 GGUF 모델(수 GB)
다운로드와 추론 연결은 사용자가 직접 진행하도록 남겨두었다. 다음과 같은 구현체를
`stub_components`의 `NoopKeywordGenerator()` 자리에 대신 주입하면 된다:

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
- 생성 품질을 정성 검수하려면 `tests/fixtures/typo_synonym_pairs.json`을 활용한다.

### 저사양 환경 검증

`docker-compose.yml`의 `ai-worker` 서비스는 `deploy.resources.limits`로 CPU/메모리를
캡핑해두었다. 실모델(E5/Qwen)을 연결한 뒤에는 실제 저사양 vCPU/RAM 환경에서 해당
제한값으로 배치가 안정적으로 도는지 별도로 검증하는 것을 권장한다.

## License

MIT © 2026 yogurt-c
