# semantic-ac

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> GPU 없이도 오타 교정과 문맥 기반 검색어 자동완성을 어떤 서비스에도 붙일 수 있는
> 오픈소스 셀프호스팅 툴킷

## 왜 필요한가

기존 Trie 기반 검색어 자동완성은 입력이 정확히 일치해야만 동작해 오타나 문맥적
유의어(예: "노트북" 입력 시 "맥북" 추천)를 처리하지 못합니다. 그렇다고 실시간
검색창에 LLM을 직접 붙이면 클라이언트 부담, GPU 비용, 응답 지연이 커져 실사용이
어렵습니다.

semantic-ac는 추천 사전을 오프라인 배치에서 sLLM과 임베딩으로 미리 컴파일해두고,
실시간 서빙은 Redis 캐시로 처리하는 방식으로 이 문제를 해결합니다. 무거운 연산은
전부 배치 쪽으로 밀어내고, 서빙 경로는 `GET`/`SET` 수준의 단순한 Redis 조회만
남깁니다.

## 아키텍처

```mermaid
flowchart LR
    subgraph Client["브라우저 / 앱"]
        SDK["@semantic-ac/client\n(debounce, 캐시, trackSearch)"]
    end

    subgraph Serving["실시간 서빙 (FastAPI)"]
        API["/suggest, /track"]
    end

    subgraph Storage["저장소"]
        Redis[("Redis\nsugg:{prefix}")]
        DuckDB[("DuckDB\nsearch_events")]
    end

    subgraph Batch["비동기 AI 배치 엔진 (Python)"]
        Runner["scoring -> embedding/Faiss\n-> keyword generator"]
    end

    SDK -- "GET /suggest?q=" --> API
    SDK -- "POST /track" --> API
    API -- "GET sugg:{prefix}" --> Redis
    API -- "적재" --> DuckDB
    Runner -- "읽기" --> DuckDB
    Runner -- "SET sugg:{prefix}" --> Redis
```

| 레이어 | 패키지 | 역할 |
|---|---|---|
| Client SDK | [`@semantic-ac/client`](packages/client) (TypeScript) | debounce 제어, 세션 내 로컬 캐싱, 검색 이벤트 트래킹 |
| 실시간 서빙 API | [`search-server`](packages/server) (FastAPI + Redis) | 자동완성 O(1) 서빙, 검색 로그 수집(DuckDB) |
| 비동기 AI 배치 엔진 | [`ai-engine`](packages/ai-engine) (Python) | 로그 스코어링, 임베딩 기반 유사어 매칭, sLLM 기반 오타/문맥 사전 컴파일 |

세 컴포넌트는 [`docs/CONTRACT.md`](docs/CONTRACT.md)에 정의된 API 스키마와 Redis 키
포맷만으로 통신하므로, 서로 독립적으로 교체하거나 배포할 수 있습니다.

## 빠른 시작

### 준비물

- Docker / Docker Compose
- (SDK를 직접 빌드하거나 수정하려는 경우) Node.js 18+, [pnpm](https://pnpm.io)
- (Python 패키지를 직접 실행/수정하려는 경우) [uv](https://docs.astral.sh/uv/)

### 전체 스택 실행

```bash
docker compose up -d --build --wait
```

- `redis`, `search-server`(FastAPI, `:8000`), `ai-worker`(배치) 세 서비스가 뜹니다.
- `ai-worker`는 기본적으로 `stub_components`의 placeholder 구현체(`HashingEmbeddingModel`,
  `NoopKeywordGenerator`)로 배치 파이프라인의 구조만 검증합니다. 실제 임베딩/sLLM
  모델을 연결하는 방법은 [`packages/ai-engine/README.md`](packages/ai-engine/README.md#로드맵)를 참고하세요.

동작 확인:

```bash
curl -X POST http://localhost:8000/track \
  -H 'Content-Type: application/json' \
  -d '{"prefix": "노트북", "selected": "가성비 노트북", "action": "final_search"}'

# ai-worker가 배치를 1회 이상 실행한 뒤
curl 'http://localhost:8000/suggest?q=노트북'
```

전체 트랙(SDK → API → Redis → 배치)을 자동으로 검증하는 E2E 스크립트:

```bash
./scripts/e2e.sh
```

### 클라이언트 SDK 설치

```bash
pnpm add @semantic-ac/client
```

사용법은 [`packages/client/README.md`](packages/client/README.md)를 참고하세요. 기존
검색창에 실제로 연결하는 러너블 예제는 [`examples/vanilla`](examples/vanilla)에
있습니다.

## 내 서비스에 적용하기

### 1. 배포

docker-compose 세 서비스(`redis`, `search-server`, `ai-worker`)를 자사 인프라에
띄웁니다. 최소한 아래 두 환경 변수는 반드시 실서비스 값으로 바꿔야 합니다
(`docker-compose.yml` 참고).

| 환경 변수 | 데모 기본값 | 실서비스에서 해야 할 일 |
|---|---|---|
| `ALLOWED_ORIGINS` | `*` | 자사 프런트엔드 도메인으로 좁히기 (콤마로 여러 개 가능) |
| `DUCKDB_PATH` | 컨테이너 내부 임시 경로 | 영구 볼륨에 마운트 (재시작 시 검색 로그가 사라지지 않도록) |

`search-server`/`ai-engine`의 나머지 환경 변수는 각 패키지 README를 참고하세요.

### 2. 프런트엔드에 SDK 연결

기존 검색 input에 debounce/캐싱/트래킹까지 포함해 실제로 연결하는 전체 흐름은
[`examples/vanilla`](examples/vanilla)에서 바로 실행해볼 수 있습니다. API 상세는
[`packages/client/README.md`](packages/client/README.md) 참고.

### 3. 콜드 스타트 이해하기

배포 직후에는 아직 검색 로그가 없으므로 `ai-worker`가 생성한 추천 사전도 비어
있습니다. 이 상태에서 `suggest()`는 에러가 아니라 **빈 배열**을 반환합니다 — 프런트
엔드는 이를 "추천 없음"으로 정상 처리해야 합니다(드롭다운을 숨기면 됩니다). 실제
사용자가 검색을 몇 번 하고(→ `trackSearch` 로그 누적), 배치가 최소 1회 실행된
뒤부터(기본 주기 60초, `BATCH_INTERVAL_SECONDS`) 추천이 채워지기 시작합니다.

### 4. 운영 체크리스트

- **HTTPS**: 이 저장소는 평문 HTTP만 서빙합니다. nginx/Caddy 등 리버스 프록시를
  앞단에 두고 TLS를 종단하세요.
- **CORS**: `ALLOWED_ORIGINS`를 자사 도메인으로 제한했는지 다시 확인하세요.
- **배치 리소스**: `docker-compose.yml`의 `ai-worker` `deploy.resources.limits`와
  `BATCH_INTERVAL_SECONDS`를 트래픽 규모에 맞게 조정하세요
  ([`packages/ai-engine/README.md`](packages/ai-engine/README.md) 참고).
- **독립성**: `redis`/DuckDB 볼륨은 이 툴킷 전용입니다. 메인 서비스의 DB나 검색
  엔진 구조를 바꿀 필요가 없습니다.

## 저장소 구조

```
.
├── docker-compose.yml       redis / search-server / ai-worker 오케스트레이션
├── docs/CONTRACT.md         트랙 간 공유 API/Redis 계약
├── examples/vanilla/        기존 input에 SDK를 붙이는 러너블 예제
├── packages/
│   ├── client/              @semantic-ac/client (TypeScript SDK)
│   ├── server/               search-server (FastAPI)
│   └── ai-engine/           ai-engine (Python 배치 파이프라인)
├── scripts/e2e.sh           전체 스택 E2E 실행 스크립트
└── tests/e2e/run.mjs        E2E 검증 로직
```

## 개발

이 저장소는 pnpm 워크스페이스(TypeScript)와 두 개의 독립적인 uv 프로젝트(Python)로
구성되어 있습니다. 각 패키지는 자체 테스트 스위트를 갖습니다.

```bash
# TypeScript (client SDK)
pnpm install
pnpm -r test

# FastAPI 서버
cd packages/server && uv sync && uv run pytest

# AI 배치 엔진
cd packages/ai-engine && uv sync --group dev && uv run pytest
```

기여 방법은 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 참고하세요.

## License

[MIT](LICENSE) © 2026 yogurt-c
