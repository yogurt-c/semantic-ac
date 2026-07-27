# @semantic-ac/client

Lightweight TypeScript SDK for context-aware, typo-tolerant search autocomplete.

## Install

```bash
pnpm add @semantic-ac/client
```

## Usage

```ts
import { SemanticAutocompleteClient, DebounceCancelledError } from "@semantic-ac/client";

const client = new SemanticAutocompleteClient({
  baseUrl: "https://api.example.com",
  debounceMs: 150, // optional, default 150
  cacheMaxEntries: 500, // optional, default 500
});
```

### `suggest(prefix)`

Resolves with cached suggestions immediately. On a cache miss it waits out
the debounce window before calling the server.

**Important:** if `suggest()` is called again before a previous call's
debounce window has elapsed, the previous call's promise rejects with
`DebounceCancelledError` instead of hanging forever. This is expected
behavior for an autocomplete input (only the latest keystroke's request
matters), but callers **must** handle the rejection — an unhandled
`DebounceCancelledError` becomes an unhandled promise rejection.

```ts
async function onInputChange(prefix: string) {
  try {
    const suggestions = await client.suggest(prefix);
    render(suggestions);
  } catch (err) {
    if (err instanceof DebounceCancelledError) {
      // A newer keystroke superseded this call — safe to ignore.
      return;
    }
    // A real failure (network error, bad response shape, etc.)
    reportError(err);
  }
}
```

### `trackSearch(prefix, selected, action)`

Fire-and-forget event tracking. The call does not need to be awaited to
avoid blocking the UI, but the returned promise still rejects on failure
(network error or non-2xx response) — errors are never swallowed. If you
don't await it, attach a `.catch()` so a failure doesn't surface as an
unhandled promise rejection:

```ts
// Fire-and-forget, but still handle failure explicitly.
client
  .trackSearch(prefix, selectedSuggestion, "suggestion_click")
  .catch((err) => reportError(err));

// Or, if you want to wait for confirmation:
await client.trackSearch(prefix, finalQuery, "final_search");
```
