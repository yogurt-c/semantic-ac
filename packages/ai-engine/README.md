# ai-engine

비동기 AI 배치 엔진. [`search-server`](../server)가 DuckDB `search_events` 테이블에
적재한 검색 로그를 읽어, 빈도+최신성 기반으로 키워드를 스코어링하고, 세션
co-occurrence로 실제 사용자 행동에서 연관 검색어를 학습하고, 임베딩/Faiss로
의미적 연관 키워드를 찾아, 오타/문맥 연관 키워드를 보강한 뒤 Redis에 자동완성
사전(`sugg:{prefix}`)을 원자적으로 기록하는 배치 파이프라인이다. 상시 실행 서버가
아니라 주기 실행되는 원샷 작업으로 설계되어 있다 (스키마는
[`../../docs/CONTRACT.md`](../../docs/CONTRACT.md) 참고).

## 추천 검색어가 만들어지는 방식

같은 prefix 안에서의 빈도/최신성만으로는 "노트북"을 검색하는 사람에게 "맥북"
같이 문자열이 겹치지 않는 진짜 연관 검색어를 추천할 수 없다. 이를 위해
`cooccurrence.py`가 `session_id`로 묶인 검색 로그에서 같은 세션에 함께
selected된 키워드 쌍을 지수 감쇠 가중치로 누적해 학습한다 — 최근에, 더 많은
세션에서 함께 검색될수록 연관 점수가 강해지고, 오래된 관계는 자연히 약해진다.
`session_id`는 클라이언트 SDK가 인스턴스 생성 시 1회 발급해 모든 `trackSearch()`
호출에 실어 보낸다 (`docs/CONTRACT.md` 섹션 2).

```
score(A, B) = Σ_세션(A,B 함께 selected) 0.5 ^ (age_hours / half_life_hours)
```

`pipeline.run_batch`는 prefix별 상위 완성어(`score_keywords`)를 seed로 삼아 이
co-occurrence 그래프에서 연관 키워드를 끌어온 뒤, 임베딩/Faiss 의미 유사도와
LLM 생성 오타 후보를 함께 병합한다.

### 예시로 보는 최종 결과

"노트북"과 "맥북"이 같은 세션에서 함께 selected된 로그가 충분히 쌓였다고 하면,
prefix `"노"`에 대해 `sugg:노`가 다음과 같은 순서로 채워진다:

```json
["노트북", "노트북 추천", "맥북", "labtop"]
```

각 항목이 어느 레이어에서 온 것인지 순서대로:

1. `"노트북"`, `"노트북 추천"` — **prefix 랭킹**(`score_keywords`): `"노"`로
   시작한 사람들이 과거에 자주/최근에 selected한 완성어. 로그가 조금만 쌓여도
   채워진다.
2. `"맥북"` — **co-occurrence**(`cooccurrence.py`): `"노트북"`과 같은 세션에서
   자주 함께 selected된 키워드. 문자열은 전혀 안 겹치지만 실제 행동 데이터로
   연결된 것이라, 세션 로그가 어느 정도 쌓여야 나타나기 시작한다.
3. `"labtop"` — **KeywordGenerator**(LLM): Faiss로 찾은 의미적 인접 키워드를
   context로 받아 생성한 오타 후보. 현재 기본값인 `NoopKeywordGenerator`는
   항상 빈 값을 반환하므로 실모델을 연결해야 실제로 채워진다([로드맵](#로드맵)).

`_merge_unique`가 이 순서(prefix 랭킹 → co-occurrence → LLM 생성)대로 병합하며
중복을 제거하고, 최종적으로 `top_n`개(기본 10개, `SUGGESTION_TOP_N`로 조정)로
자른다.

## 기술 스택

- 임베딩 모델: `intfloat/multilingual-e5-small`
- Vector DB: Faiss (라이브러리 내장, 별도 서버 프로세스 없음)
- sLLM: Llama.cpp + Qwen2.5-1.5B-GGUF (4-bit 양자화) — 연결 방법은 아래 [로드맵](#로드맵) 참고

## Structure

```
src/ai_engine/
  events.py             SearchEvent (search_events 레코드 1건, session_id 포함)
  db_reader.py           DuckDB search_events 테이블 읽기 (read-only)
  scoring.py             빈도+최신성 스코어링 순수 함수 (DB 비의존)
  cooccurrence.py        세션 co-occurrence 기반 연관 검색어 학습 (DB 비의존)
  embeddings.py          EmbeddingModel Protocol + E5SmallEmbeddingModel(실제 통합 지점)
  vector_index.py        Faiss 인덱스 빌드 / 원자적 저장(os.replace) / 최근접 검색
  keyword_generator.py   KeywordGenerator Protocol (오타/문맥 연관 키워드 생성)
  redis_writer.py        sugg:{prefix} 원자적 SET (docs/CONTRACT.md 섹션 3)
  pipeline.py            스코어링 -> co-occurrence -> 임베딩/Faiss -> KeywordGenerator -> Redis 조립
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

## 환경 변수

`runner.py`(배치 실행 진입점)가 읽는 환경 변수. docker-compose에서는 `ai-worker`
서비스의 `environment:`에 설정한다(`docker-compose.yml` 참고). 코드를 고치지
않고도 추천 생성 방식을 자사 트래픽에 맞게 조정할 수 있다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | 추천 결과를 쓸 Redis |
| `DUCKDB_PATH` | `data/search_events.duckdb` | 읽어올 검색 로그 DB(`search-server`와 같은 파일 공유) |
| `INDEX_PATH` | `data/index.faiss` | Faiss 인덱스 파일 경로 |
| `BATCH_INTERVAL_SECONDS` | `60` | 배치 반복 주기(초). `--once`와 함께 쓰지 않음 |
| `SUGGESTION_TOP_N` | `10` | prefix당 최종 추천 개수 |
| `FAISS_CONTEXT_SIZE` | `5` | `KeywordGenerator`에 넘길 Faiss 최근접 키워드 개수 |
| `COOCCURRENCE_HALF_LIFE_HOURS` | `168`(1주) | 연관 검색어(co-occurrence) 점수의 감쇠 반감기. 짧게 하면 최신 트렌드에 더 민감해지지만 데이터가 적을 때는 관계가 빨리 사라진다 |
| `COOCCURRENCE_SEED_SIZE` | `3` | prefix당 co-occurrence 조회에 seed로 쓸 상위 완성어 개수 |

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
