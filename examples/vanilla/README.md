# vanilla JS 예제

프레임워크 없이 `@semantic-ac/client`를 실제 `<input>`에 연결하는 최소 예제.
[`index.html`](index.html)이 하는 일 전부: 입력 → `suggest()` → 드롭다운 렌더링 →
클릭/Enter 시 `trackSearch()`.

## 실행

1. 저장소 루트에서 docker-compose 스택을 띄운다.

   ```bash
   docker compose up -d --build --wait
   ```

2. 클라이언트 SDK를 빌드한다 (이 예제는 `packages/client/dist`를 상대 경로로 직접
   불러온다).

   ```bash
   pnpm --filter @semantic-ac/client build
   ```

3. 정적 파일 서버로 저장소 루트를 서빙한다. `index.html`을 `file://`로 직접 열면
   브라우저가 ES 모듈 import를 CORS 정책으로 막으므로, 반드시 http로 서빙해야 한다.

   ```bash
   python3 -m http.server 5500
   ```

4. 브라우저에서 `http://localhost:5500/examples/vanilla/` 접속.

콜드 스타트 없이 co-occurrence/오타 교정 데모를 바로 보고 싶다면 3번 대신
[`scripts/seed-demo-data`](../../scripts/seed-demo-data)를 사용하세요 (루트
[`README.md`](../../README.md#데모-데이터로-바로-체험하기) 참고).

## 참고

- docker-compose의 `search-server`는 기본적으로 `ALLOWED_ORIGINS=*`로 뜨기 때문에,
  이 예제를 어떤 포트에서 서빙하든 CORS 문제 없이 바로 붙는다. 자사 서비스에 실제로
  적용할 때는 이 값을 자사 도메인으로 좁혀야 한다 (`packages/server/README.md` 참고).
- 아직 배치가 한 번도 돌지 않았다면 `suggest()`는 항상 빈 배열을 반환한다. 먼저
  검색어를 입력하고 Enter를 눌러 `trackSearch` 이벤트를 몇 개 쌓은 뒤, 배치를 1회
  실행해야 추천이 보인다.

  ```bash
  docker compose run --rm ai-worker python -m ai_engine.runner --once
  ```
