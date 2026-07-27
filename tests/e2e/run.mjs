// 트랙 A(SDK) -> 트랙 B(FastAPI/Redis/DuckDB) -> 트랙 C(AI 배치 엔진) 전체 통합을
// 실제 docker-compose 스택 + 컴파일된 SDK로 검증하는 E2E 테스트.
// 실행 전제: `docker compose up -d --build --wait` 로 스택이 떠 있어야 한다.
// 실행: node tests/e2e/run.mjs (scripts/e2e.sh 가 오케스트레이션함)

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SemanticAutocompleteClient } from "../../packages/client/dist/index.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:8000";

function runBatchOnce() {
  execFileSync(
    "docker",
    ["compose", "run", "--rm", "ai-worker", "python", "-m", "ai_engine.runner", "--once"],
    { cwd: REPO_ROOT, stdio: "inherit" },
  );
}

async function main() {
  // 재실행해도 이전 실행의 누적 데이터와 섞이지 않도록 매번 고유한 prefix를 쓴다.
  const prefix = `e2e-${Date.now()}`;
  const trackClient = new SemanticAutocompleteClient({ baseUrl: BASE_URL, debounceMs: 0 });

  console.log(`[e2e] trackSearch 이벤트 전송 (prefix=${prefix})`);
  await trackClient.trackSearch(prefix, `${prefix} 인기 제안`, "suggestion_click");
  await trackClient.trackSearch(prefix, `${prefix} 인기 제안`, "suggestion_click");
  await trackClient.trackSearch(prefix, `${prefix} 확정 검색어`, "final_search");

  // suggest() 결과는 세션 내 인메모리 캐시에 저장되므로(트랙 A 기능), 배치 전/후
  // 시점을 각각 검증하려면 서로 다른 클라이언트 인스턴스를 써야 한다.
  console.log("[e2e] 배치 실행 전 suggest는 빈 배열이어야 한다");
  const beforeClient = new SemanticAutocompleteClient({ baseUrl: BASE_URL, debounceMs: 0 });
  const beforeBatch = await beforeClient.suggest(prefix);
  assert.deepEqual(beforeBatch, [], `배치 실행 전인데 이미 suggestion이 존재: ${beforeBatch}`);

  console.log("[e2e] ai-worker 배치 1회 실행 (트랙 C)");
  runBatchOnce();

  console.log("[e2e] 배치 실행 후 suggest 결과 확인");
  const afterClient = new SemanticAutocompleteClient({ baseUrl: BASE_URL, debounceMs: 0 });
  const suggestions = await afterClient.suggest(prefix);
  assert.ok(suggestions.length > 0, "배치 실행 후에도 suggestion이 비어 있음");
  assert.ok(
    suggestions.includes(`${prefix} 인기 제안`),
    `빈도가 더 높은 키워드가 suggestions에 없음: ${JSON.stringify(suggestions)}`,
  );
  assert.ok(
    suggestions.includes(`${prefix} 확정 검색어`),
    `final_search 키워드가 suggestions에 없음: ${JSON.stringify(suggestions)}`,
  );

  console.log("[e2e] PASS -", JSON.stringify(suggestions));
}

main().catch((error) => {
  console.error("[e2e] FAIL -", error);
  process.exitCode = 1;
});
