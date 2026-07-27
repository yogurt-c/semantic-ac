# search-server

실시간 서빙 레이어 (FastAPI). Redis에서 완성형 추천어를 O(1)로 조회하고, SDK가 보낸 학습용
이벤트를 메인 서비스 DB와 분리된 DuckDB 파일에 적재한다. [`ai-engine`](../ai-engine)이
같은 DuckDB 파일을 읽어 배치를 생성하고, 같은 Redis 키 포맷으로 결과를 쓴다. 세 패키지가
공유하는 스키마는 [`../../docs/CONTRACT.md`](../../docs/CONTRACT.md)에 정의되어 있다.

## Setup

```bash
uv sync
```

## Run

```bash
export REDIS_URL=redis://localhost:6379/0   # 기본값
export DUCKDB_PATH=data/search_events.duckdb # 기본값
uv run uvicorn search_server.main:app --reload
```

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | 자동완성 사전(`sugg:{prefix}`)을 조회할 Redis 연결 문자열 |
| `DUCKDB_PATH` | `data/search_events.duckdb` | 검색 이벤트를 적재할 DuckDB 파일 경로. `ai-engine`과 동일한 경로를 공유해야 함 |
| `ALLOWED_ORIGINS` | `*` | CORS 허용 origin. 콤마로 구분해 여러 개 지정 가능(예: `https://shop.example.com,https://m.shop.example.com`). 프런트엔드가 이 서버와 다른 origin에서 `/suggest`, `/track`을 호출하는 실서비스 환경에서는 반드시 자사 도메인으로 좁혀서 지정할 것 |

## Test

```bash
uv run pytest
```

`pyproject.toml`에 커버리지 80% 미만이면 실패하도록 `--cov-fail-under=80`이 기본 설정되어 있다.

## Structure

```
src/search_server/
  main.py            FastAPI 앱 팩토리 (create_app)
  config.py          환경 변수 로딩
  models.py          요청/응답 Pydantic 모델
  redis_client.py    Redis 연결
  db.py              DuckDB 연결 (요청 단위로 열고 닫음 — 프로세스 간 파일 락 회피)
  routers/
    suggest.py       GET /suggest
    track.py         POST /track
```

## Endpoints

- `GET /suggest?q={prefix}` — Redis 키 `sugg:{prefix}` 조회
- `POST /track` — `search_events(prefix, selected, action, event_ts, session_id)`를 DuckDB에 적재

## License

MIT © 2026 yogurt-c
