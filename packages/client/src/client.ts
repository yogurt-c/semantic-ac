import { PrefixCache } from "./cache.js";
import { debounce } from "./debounce.js";
import { DebounceCancelledError } from "./errors.js";
import { createSessionId } from "./session-id.js";
import { trackSearch, type TrackAction } from "./track.js";

const DEFAULT_DEBOUNCE_MS = 150;

export interface SemanticAutocompleteClientOptions {
  baseUrl: string;
  debounceMs?: number;
  cacheMaxEntries?: number;
  fetchImpl?: typeof fetch;
  /**
   * AI 배치 엔진의 co-occurrence 학습(같은 세션에서 함께 selected된 키워드 묶기)이
   * 쓰는 상관키. 생략하면 클라이언트 인스턴스당 1회 자동 발급되어 이 인스턴스의
   * 모든 trackSearch() 호출에 동일하게 실린다. 서버 세션 등 직접 관리하고 싶을 때만 넘긴다.
   */
  sessionId?: string;
}

interface SuggestResponseBody {
  suggestions: string[];
}

function isSuggestResponseBody(data: unknown): data is SuggestResponseBody {
  if (typeof data !== "object" || data === null || !("suggestions" in data)) {
    return false;
  }
  const { suggestions } = data as { suggestions: unknown };
  return Array.isArray(suggestions) && suggestions.every((item) => typeof item === "string");
}

export class SemanticAutocompleteClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly cache: PrefixCache<string[]>;
  private readonly debouncedFetch: (prefix: string) => void;
  private readonly sessionId: string;

  private pendingResolve: ((suggestions: string[]) => void) | undefined;
  private pendingReject: ((reason: unknown) => void) | undefined;

  constructor(options: SemanticAutocompleteClientOptions) {
    this.baseUrl = options.baseUrl;
    // `fetch` is a "branded" built-in in browsers — calling it as `this.fetchImpl(url)`
    // detaches it from `window` and throws `TypeError: Illegal invocation`. Bind the
    // default to globalThis so it survives being stored as a method.
    this.fetchImpl = options.fetchImpl ?? fetch.bind(globalThis);
    this.sessionId = options.sessionId ?? createSessionId();
    this.cache = new PrefixCache<string[]>(options.cacheMaxEntries);
    this.debouncedFetch = debounce((prefix: string) => {
      void this.executeFetch(prefix);
    }, options.debounceMs ?? DEFAULT_DEBOUNCE_MS);
  }

  /**
   * Resolves with cached suggestions immediately, otherwise waits out the
   * debounce window before fetching. If this method is called again with a
   * pending (not-yet-fetched) prior call still in flight, that prior call's
   * promise rejects with {@link DebounceCancelledError} instead of hanging
   * forever. Callers MUST handle that rejection (e.g. `.catch` or
   * `try/catch`) — an ignored cancellation becomes an unhandled promise
   * rejection.
   */
  suggest(prefix: string): Promise<string[]> {
    const cached = this.cache.get(prefix);
    if (cached !== undefined) {
      return Promise.resolve(cached);
    }

    this.cancelPending();

    return new Promise<string[]>((resolve, reject) => {
      this.pendingResolve = resolve;
      this.pendingReject = reject;
      this.debouncedFetch(prefix);
    });
  }

  /**
   * Fire-and-forget event tracking (POST {baseUrl}/track). Safe to call
   * without awaiting, but the returned promise rejects if the request
   * fails or the server responds with a non-2xx status — errors are never
   * swallowed. Attach a `.catch()` if the call site does not await this,
   * otherwise a failure surfaces as an unhandled promise rejection.
   */
  async trackSearch(prefix: string, selected: string, action: TrackAction): Promise<void> {
    await trackSearch(
      { baseUrl: this.baseUrl, fetchImpl: this.fetchImpl },
      { prefix, selected, action, sessionId: this.sessionId },
    );
  }

  private cancelPending(): void {
    if (this.pendingReject !== undefined) {
      this.pendingReject(new DebounceCancelledError());
    }
    this.pendingResolve = undefined;
    this.pendingReject = undefined;
  }

  private async executeFetch(prefix: string): Promise<void> {
    const resolve = this.pendingResolve;
    const reject = this.pendingReject;
    this.pendingResolve = undefined;
    this.pendingReject = undefined;

    try {
      const url = `${this.baseUrl}/suggest?q=${encodeURIComponent(prefix)}`;
      const response = await this.fetchImpl(url);
      if (!response.ok) {
        throw new Error(`suggest failed with status ${response.status}`);
      }
      const body: unknown = await response.json();
      if (!isSuggestResponseBody(body)) {
        throw new Error("invalid suggestion response shape");
      }
      this.cache.set(prefix, body.suggestions);
      resolve?.(body.suggestions);
    } catch (error) {
      reject?.(error);
    }
  }
}
