# seed-demo-data

콜드 스타트(`search_events`가 비어 있어 배치가 추천 사전을 만들지 못하는 상태) 없이
바로 co-occurrence/오타 교정 데모를 볼 수 있도록, 현실적인 샘플 검색 로그를
실행 중인 `search-server`에 주입하는 스크립트입니다.

## 구성

- `events.tsv` — 샘플 검색 로그 fixture (탭 구분: `session_id  prefix  selected  action`).
  - 그룹 A: `"노트북"` ↔ `"맥북"` co-occurrence 데모용 세션 16개.
  - 그룹 B: `"무선이어폭"→"무선이어폰"`, `"가습키"→"가습기"` 오타 교정 데모용 세션 20개.
  - 그룹 C: FAISS/Qwen 컨텍스트 어휘를 넓히기 위한 필러 검색어 10개.
- `seed.sh` — `events.tsv`를 읽어 각 행을 `POST /track`으로 전송하는 bash 스크립트.

## 사용법

```bash
docker compose up -d --build --wait   # 아직 안 띄웠다면
./scripts/seed-demo-data/seed.sh
docker compose restart ai-worker      # BATCH_INTERVAL_SECONDS(기본 60초)를 기다리지 않고
                                       # 즉시 배치 1회 실행 (runner.py는 재시작 직후 1회
                                       # 실행 후 대기 루프로 들어간다)

curl 'http://localhost:8000/suggest?q=노트북'   # ["노트북", "맥북", ...]
curl 'http://localhost:8000/suggest?q=무선이어폭' # ["무선이어폰"]
```

`SEARCH_SERVER_URL` 환경 변수로 대상 서버를 바꿀 수 있습니다(기본값
`http://localhost:8000`).

## 참고

- `/track`은 타임스탬프를 클라이언트에서 받지 않고 항상 수신 시각으로 기록하므로
  (`docs/CONTRACT.md` 섹션 2), 이 스크립트로 넣은 이벤트는 항상 "방금 발생한" 것으로
  취급되어 감쇠(half-life) 가중치가 최대치입니다.
- 실제 추천 품질(오타 교정/연관어)을 보려면 `docker-compose.yml`의 `ai-worker`가
  `EMBEDDING_PROVIDER=e5`/`KEYWORD_GENERATOR_PROVIDER=qwen` 실모델로 연결되어 있어야
  합니다 — 기본 placeholder(`hashing`/`noop`) 상태에서도 그룹 A/B의 co-occurrence·
  스코어링 기반 추천(`"노트북"→"맥북"`, `"무선이어폭"→"무선이어폰"`)은 그대로
  동작하지만, FAISS 임베딩 유사도나 Qwen 생성 후보는 나오지 않습니다. 자세한 전환
  방법은 루트 [`README.md`](../../README.md#실모델e5qwen로-전환하기) 참고.
