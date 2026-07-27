# semantic-ac

> GPU 없이도 오타 교정과 문맥 기반 검색어 자동완성을 어떤 서비스에도 붙일 수 있는 오픈소스 셀프호스팅 툴킷

## 개요

기존 Trie 기반 검색어 자동완성은 입력이 정확히 일치해야만 동작해 오타나 문맥적 유의어(예: "노트북" 입력 시 "맥북" 추천)를 처리하지 못합니다. 그렇다고 실시간 검색창에 LLM을 직접 붙이면 클라이언트 부담, GPU 비용, 응답 지연이 커져 실사용이 어렵습니다.

semantic-ac는 추천 사전을 오프라인 배치에서 sLLM과 임베딩으로 미리 컴파일해두고, 실시간 서빙은 Redis 캐시로 처리하는 방식으로 이 문제를 해결합니다.

## 아키텍처

- **Client SDK** (`@semantic-ac/client`, TypeScript): debounce 제어, 세션 내 로컬 캐싱, 검색 이벤트 트래킹
- **실시간 서빙 API** (FastAPI + Redis): 자동완성 O(1) 서빙, 검색 로그 수집(DuckDB/SQLite)
- **비동기 AI 배치 엔진** (Python + Llama.cpp): 로그 스코어링, 임베딩 기반 유사어 매칭, sLLM 기반 오타/문맥 사전 컴파일

## 실행 (docker-compose)

```bash
docker compose up -d --build --wait
```

- `redis`, `search-server`(FastAPI, :8000), `ai-worker`(배치) 3개 서비스가 뜬다.
- `ai-worker`는 실모델(E5/Qwen) 연결 전까지 `stub_components` placeholder로 배치
  파이프라인 구조만 검증한다 (`packages/ai-engine/README.md` 참고).
- 전체 트랙(SDK → API → Redis → 배치) E2E 검증: `./scripts/e2e.sh`

## 상태

Client SDK / FastAPI 서버 / AI 배치 엔진 3개 트랙과 docker-compose 통합, E2E
테스트까지 구축된 상태입니다. 남은 작업은 [`TODO.md`](TODO.md) 참고.

## License

MIT © 2026 yogurt-c
