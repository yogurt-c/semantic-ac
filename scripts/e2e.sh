#!/usr/bin/env bash
# 트랙 A(SDK) -> 트랙 B(FastAPI/Redis/DuckDB) -> 트랙 C(AI 배치 엔진) E2E 통합 테스트.
# docker-compose 스택을 깨끗한 상태로 띄우고 tests/e2e/run.mjs를 실행한 뒤 정리한다.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

cleanup() {
  echo "[e2e] docker compose down -v"
  docker compose down -v
}
trap cleanup EXIT

echo "[e2e] docker compose up (build) --wait"
docker compose up -d --build --wait

echo "[e2e] client SDK 빌드"
pnpm --filter @semantic-ac/client build

echo "[e2e] E2E 테스트 실행"
node tests/e2e/run.mjs
