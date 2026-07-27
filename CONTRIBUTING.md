# Contributing to semantic-ac

이 프로젝트는 세 개의 독립적인 패키지(Client SDK / 서빙 API / AI 배치 엔진)로
구성됩니다. 기여하기 전에 각 패키지가 어떻게 통신하는지 정의한
[`docs/CONTRACT.md`](docs/CONTRACT.md)를 먼저 읽어주세요 — API 스키마와 Redis 키
포맷은 이 문서를 갱신하지 않고는 변경할 수 없습니다.

## 개발 환경 준비

| 대상 | 필요 도구 |
|---|---|
| `packages/client` | Node.js 18+, [pnpm](https://pnpm.io) |
| `packages/server` | Python 3.13+, [uv](https://docs.astral.sh/uv/) |
| `packages/ai-engine` | Python 3.11–3.12, [uv](https://docs.astral.sh/uv/) |
| 전체 스택 통합 확인 | Docker / Docker Compose |

## 패키지별 테스트 실행

```bash
# Client SDK
cd packages/client
pnpm install
pnpm test          # vitest + 커버리지

# search-server
cd packages/server
uv sync
uv run pytest      # --cov-fail-under=80

# ai-engine
cd packages/ai-engine
uv sync --group dev
uv run pytest      # --cov-fail-under=80
```

전체 스택을 docker-compose로 띄운 뒤 트랙 간 연동을 확인하려면:

```bash
./scripts/e2e.sh
```

## PR 체크리스트

- [ ] 변경한 패키지의 테스트가 통과하고, 커버리지가 80% 이상 유지되는가
- [ ] `docs/CONTRACT.md`에 정의된 API/Redis 스키마를 깨뜨리지 않았는가 (변경이
      필요하다면 이 문서를 먼저 갱신)
- [ ] 여러 패키지에 걸친 변경이라면 `./scripts/e2e.sh`로 통합 동작을 확인했는가
- [ ] 관련 패키지의 README를 함께 갱신했는가

## 커밋 메시지

`<type>: <description>` 형식을 사용합니다 (예: `feat: add debounce cancellation`).
`type`은 `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci` 중 하나를
사용합니다.

## 이슈 및 버그 리포트

버그를 발견했다면 재현 절차와 함께 GitHub Issue로 등록해 주세요. 어떤 패키지에서
발생했는지(client / server / ai-engine), docker-compose 스택 기준인지 개별 패키지
기준인지 명시해 주시면 도움이 됩니다.
