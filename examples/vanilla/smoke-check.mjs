// examples/vanilla/index.html이 사용하는 것과 동일한 상대 경로로 클라이언트 SDK를
// import해, 예제가 참조하는 dist 경로/export가 여전히 유효한지 검증하는 가벼운
// 스모크 체크. (실제 suggest/track 동작 자체는 tests/e2e/run.mjs가 검증한다 —
// 여기서는 "예제가 참조하는 경로"만 별도로 지킨다.)
// 실행: node examples/vanilla/smoke-check.mjs (scripts/e2e.sh 가 오케스트레이션함)

import assert from "node:assert/strict";

import { SemanticAutocompleteClient, DebounceCancelledError } from "../../packages/client/dist/index.js";

assert.equal(typeof SemanticAutocompleteClient, "function", "SemanticAutocompleteClient export 누락");
assert.equal(typeof DebounceCancelledError, "function", "DebounceCancelledError export 누락");

const client = new SemanticAutocompleteClient({ baseUrl: "http://localhost:8000" });
assert.equal(typeof client.suggest, "function", "suggest() 메서드 누락");
assert.equal(typeof client.trackSearch, "function", "trackSearch() 메서드 누락");

console.log("[examples/vanilla] smoke check PASS - import path와 API 형태가 유효함");
