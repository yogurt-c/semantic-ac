# 공유 인터페이스 계약 (Track A/B/C 공통 기준)

이 문서에 정의된 스키마는 클라이언트 SDK(트랙 A), FastAPI 서버(트랙 B), AI 배치 엔진(트랙 C)이
서로 독립적으로 개발하면서도 통합 시점에 어긋나지 않도록 하는 단일 기준이다. 세 트랙 모두
아래 스키마를 변경 없이 그대로 구현/소비해야 하며, 변경이 필요하면 이 문서를 먼저 갱신한다.

## 1. Suggestion API (트랙 B 구현 / 트랙 A 소비)

```
GET {baseUrl}/suggest?q={prefix}
```

- `q`: 필수, URL-인코딩된 미완성 입력어(빈 문자열 금지)
- 응답 200:
  ```json
  { "suggestions": ["노트북 추천", "가성비 노트북"] }
  ```
  - `suggestions`: `string[]`. 매칭 없으면 빈 배열(`[]`), 404 아님.
  - 정렬: 서버가 스코어 내림차순으로 정렬해 반환(클라이언트는 재정렬하지 않음).
- 에러:
  - 400: `q` 누락/빈 문자열 — `{ "error": "q is required" }`
  - 500: Redis 조회 실패 등 — `{ "error": "<message>" }`
- 성능 기준: 서버 처리 시간(Redis GET 왕복) 기준으로 측정 (TODO.md 0번 결정 참조)

## 2. Ingestion API — `trackSearch()` (트랙 B 구현 / 트랙 A 소비)

```
POST {baseUrl}/track
Content-Type: application/json
```

요청 바디:

```json
{
  "prefix": "노트북",
  "selected": "가성비 노트북",
  "action": "suggestion_click"
}
```

- `prefix`: string, 필수. 사용자가 입력한 미완성 검색어.
- `selected`: string, 필수. 클릭된 추천어 또는 최종 확정 검색어.
- `action`: `"suggestion_click" | "final_search"`, 필수.
- `timestamp`: 클라이언트는 보내지 않음. 서버가 수신 시각 기준으로 채움.
- 응답 202, 바디 없음. Fire-and-forget — 클라이언트는 응답을 기다리되 결과와 무관하게 UI를 막지 않는다.
- 서버 처리: DuckDB/SQLite `search_events(prefix, selected, action, event_ts)` 테이블에 적재. 메인
  서비스 DB와 완전히 분리된 파일 DB 사용.

## 3. Redis 키 포맷 (트랙 C가 쓰기 / 트랙 B가 읽기)

```
key:   sugg:{prefix}
value: JSON 배열의 문자열, 예: ["노트북 추천", "가성비 노트북"]
```

- 네임스페이스 접두사 `sugg:`로 공유 Redis 인스턴스 내 키 충돌 방지.
- 쓰기는 트랙 C(AI 배치 엔진)만 수행. 배치 1회 실행마다 관련된 `sugg:*` 키들을 개별 `SET`으로
  덮어쓴다. Redis의 단일 키 `SET`은 원자적이므로, 서버는 항상 "이전 값 전체" 또는 "새 값 전체"만
  읽으며 부분적으로 갱신된 상태를 볼 수 없다 — 별도의 스테이징 키/트랜잭션 불필요 (MVP 범위).
- TTL 없음. 다음 배치 사이클에서 값이 통째로 재생성/덮어쓰기됨.
- 읽기는 트랙 B(Suggestion API)만 수행, 단순 `GET sugg:{prefix}`.

## 4. 공통 규칙

- 모든 엔드포인트는 트랙 A SDK의 `baseUrl` 옵션을 prefix로 사용한다 (버저닝은 MVP 범위 밖).
- 세 트랙 모두 이 문서의 필드명/타입을 그대로 사용한다. 임의로 필드를 추가하는 것은 괜찮으나
  (예: 내부 메타데이터) 기존 필드명/타입/응답 코드를 바꾸는 것은 이 문서 갱신 없이는 금지.
