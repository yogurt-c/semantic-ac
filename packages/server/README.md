# search-server

실시간 서빙 레이어 (FastAPI). Redis에서 완성형 추천어를 O(1)로 조회하고, SDK가 보낸 학습용
이벤트를 별도 DuckDB 파일에 적재한다. 스키마는 `../../docs/CONTRACT.md`를 따른다.

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

## Test

```bash
uv run pytest
```

`pyproject.toml`에 커버리지 80% 미만이면 실패하도록 `--cov-fail-under=80`이 기본 설정되어 있다.

## Endpoints

- `GET /suggest?q={prefix}` — Redis 키 `sugg:{prefix}` 조회
- `POST /track` — `search_events(prefix, selected, action, event_ts)`를 DuckDB에 적재
