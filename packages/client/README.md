# @semantic-ac/client

문맥 인식/오타 허용 검색어 자동완성을 위한 경량 TypeScript SDK.
[semantic-ac](../../README.md) 툴킷의 일부이며, [`docs/CONTRACT.md`](../../docs/CONTRACT.md)에
정의된 스키마로 [`search-server`](../server)의 suggestion API와 짝을 이룬다.

## Install

```bash
pnpm add @semantic-ac/client
```

## Usage

```ts
import { SemanticAutocompleteClient, DebounceCancelledError } from "@semantic-ac/client";

const client = new SemanticAutocompleteClient({
  baseUrl: "https://api.example.com",
  debounceMs: 150, // 선택, 기본값 150
  cacheMaxEntries: 500, // 선택, 기본값 500
  // sessionId: "custom-id", // 선택, 생략 시 인스턴스당 1회 자동 발급(crypto.randomUUID())
});
```

**`sessionId`란?** AI 배치 엔진이 "같은 세션에서 함께 검색된 키워드"를 묶어
연관 검색어를 학습하는 유일한 상관키다(`docs/CONTRACT.md` 섹션 2). 생략하면 이
클라이언트 인스턴스의 모든 `trackSearch()` 호출에 동일한 값이 자동으로 실린다.
**한 브라우징 세션 동안은 인스턴스를 재사용해야 한다** — 검색할 때마다 새
인스턴스를 만들면 세션이 매번 끊겨 연관 검색어 학습에 필요한 신호가 만들어지지
않는다. 서버사이드 세션 등 직접 발급한 값을 쓰고 싶을 때만 명시적으로 넘기면 된다.

### `suggest(prefix)`

캐시된 추천어가 있으면 즉시 resolve한다. 캐시 미스면 debounce 윈도우가 끝난 뒤에
서버를 호출한다.

**중요:** 이전 호출의 debounce 윈도우가 아직 끝나기 전에 `suggest()`가 다시
호출되면, 이전 호출의 프로미스는 무한 대기하는 대신 `DebounceCancelledError`로
reject된다. 이는 자동완성 입력에서 기대되는 동작(가장 최신 키 입력의 요청만
유효)이지만, 호출자는 이 reject를 **반드시** 처리해야 한다 — 처리하지 않은
`DebounceCancelledError`는 처리되지 않은 프로미스 거부(unhandled promise
rejection)로 이어진다.

```ts
async function onInputChange(prefix: string) {
  try {
    const suggestions = await client.suggest(prefix);
    render(suggestions);
  } catch (err) {
    if (err instanceof DebounceCancelledError) {
      // 더 최신 키 입력이 이 호출을 대체함 — 무시해도 안전하다.
      return;
    }
    // 실제 실패(네트워크 오류, 잘못된 응답 형식 등)
    reportError(err);
  }
}
```

### `trackSearch(prefix, selected, action)`

Fire-and-forget 방식의 이벤트 트래킹이다. UI를 막지 않기 위해 await할 필요는
없지만, 반환된 프로미스는 실패 시(네트워크 오류 또는 non-2xx 응답) 여전히
reject되며 — 오류를 절대 삼키지 않는다. await하지 않는다면, 실패가 처리되지 않은
프로미스 거부로 드러나지 않도록 `.catch()`를 붙여야 한다. 생성자의 `sessionId`
(위 참고)가 매 호출에 자동으로 실리므로 호출자가 직접 넘길 필요는 없다:

```ts
// Fire-and-forget이지만, 실패는 명시적으로 처리한다.
client
  .trackSearch(prefix, selectedSuggestion, "suggestion_click")
  .catch((err) => reportError(err));

// 또는 확인을 기다리고 싶다면:
await client.trackSearch(prefix, finalQuery, "final_search");
```

## Development

```bash
pnpm install
pnpm test        # vitest + 커버리지
pnpm build        # dist/ 산출 (tsc)
pnpm typecheck
```

## License

MIT © 2026 yogurt-c
