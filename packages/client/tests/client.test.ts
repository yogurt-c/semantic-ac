import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SemanticAutocompleteClient } from "../src/client";
import { DebounceCancelledError } from "../src/errors";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response;
}

describe("SemanticAutocompleteClient", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("waits for the debounce window before calling fetch", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ suggestions: [] }));
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    void client.suggest("노트");
    await vi.advanceTimersByTimeAsync(149);

    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("fetches suggestions with an encoded query parameter after the debounce window", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ suggestions: ["노트북 추천"] }));
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    const pending = client.suggest("노트 북");
    await vi.advanceTimersByTimeAsync(150);
    const result = await pending;

    expect(result).toEqual(["노트북 추천"]);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe(
      `https://api.example.com/suggest?q=${encodeURIComponent("노트 북")}`,
    );
  });

  it("resolves immediately from cache without calling fetch again", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ suggestions: ["노트북"] }));
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    const first = client.suggest("노트");
    await vi.advanceTimersByTimeAsync(150);
    await first;

    fetchImpl.mockClear();
    const second = await client.suggest("노트");

    expect(second).toEqual(["노트북"]);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("rejects the pending call with DebounceCancelledError when a new prefix cancels it", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ suggestions: ["나중결과"] }));
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    const firstCall = client.suggest("노트");
    await vi.advanceTimersByTimeAsync(50);

    const secondCall = client.suggest("노트북");

    await expect(firstCall).rejects.toBeInstanceOf(DebounceCancelledError);

    await vi.advanceTimersByTimeAsync(150);
    await expect(secondCall).resolves.toEqual(["나중결과"]);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("rejects when the suggest endpoint responds with a non-2xx status", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ error: "boom" }, 500));
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    const pending = client.suggest("노트");
    const expectation = expect(pending).rejects.toThrow("suggest failed with status 500");
    await vi.advanceTimersByTimeAsync(150);

    await expectation;
  });

  it("rejects when the suggest response's suggestions field is not an array", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ suggestions: "not-an-array" }));
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    const pending = client.suggest("노트");
    const expectation = expect(pending).rejects.toThrow("invalid suggestion response shape");
    await vi.advanceTimersByTimeAsync(150);

    await expectation;
  });

  it("rejects when the suggest response's suggestions array contains non-string elements", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ suggestions: ["노트북", 42] }));
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    const pending = client.suggest("노트");
    const expectation = expect(pending).rejects.toThrow("invalid suggestion response shape");
    await vi.advanceTimersByTimeAsync(150);

    await expectation;
  });

  it("propagates fetch errors instead of swallowing them", async () => {
    const networkError = new Error("network down");
    const fetchImpl = vi.fn().mockRejectedValue(networkError);
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    const pending = client.suggest("노트");
    const expectation = expect(pending).rejects.toThrow("network down");
    await vi.advanceTimersByTimeAsync(150);

    await expectation;
  });

  it("honors a custom debounceMs option", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ suggestions: [] }));
    const client = new SemanticAutocompleteClient({
      baseUrl: "https://api.example.com",
      debounceMs: 300,
      fetchImpl,
    });

    void client.suggest("노트");
    await vi.advanceTimersByTimeAsync(150);
    expect(fetchImpl).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(150);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("defaults to a fetch implementation that survives being detached from `this` (regression: browsers throw 'Illegal invocation' when the native fetch is called as a bare method)", async () => {
    const originalFetch = globalThis.fetch;
    const brandedFetch = function (this: unknown) {
      if (this !== globalThis) {
        throw new TypeError("Illegal invocation");
      }
      return Promise.resolve(jsonResponse({ suggestions: ["노트북"] }));
    };
    globalThis.fetch = brandedFetch as typeof fetch;

    try {
      const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com" });
      const pending = client.suggest("노트");
      await vi.advanceTimersByTimeAsync(150);
      await expect(pending).resolves.toEqual(["노트북"]);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("delegates trackSearch to POST {baseUrl}/track", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, status: 202 } as Response);
    const client = new SemanticAutocompleteClient({
      baseUrl: "https://api.example.com",
      fetchImpl,
      sessionId: "session-1",
    });

    await client.trackSearch("노트", "노트북", "suggestion_click");

    expect(fetchImpl).toHaveBeenCalledWith(
      "https://api.example.com/track",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prefix: "노트",
          selected: "노트북",
          action: "suggestion_click",
          sessionId: "session-1",
        }),
      }),
    );
  });

  it("auto-generates a sessionId and reuses it across multiple trackSearch calls", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, status: 202 } as Response);
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    await client.trackSearch("노트", "노트북", "suggestion_click");
    await client.trackSearch("맥북", "맥북 프로", "final_search");

    const firstBody = JSON.parse(fetchImpl.mock.calls[0]?.[1]?.body as string);
    const secondBody = JSON.parse(fetchImpl.mock.calls[1]?.[1]?.body as string);

    expect(firstBody.sessionId).toEqual(expect.any(String));
    expect(firstBody.sessionId.length).toBeGreaterThan(0);
    expect(secondBody.sessionId).toBe(firstBody.sessionId);
  });

  it("generates a different sessionId per client instance", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, status: 202 } as Response);
    const clientA = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });
    const clientB = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    await clientA.trackSearch("노트", "노트북", "suggestion_click");
    await clientB.trackSearch("노트", "노트북", "suggestion_click");

    const bodyA = JSON.parse(fetchImpl.mock.calls[0]?.[1]?.body as string);
    const bodyB = JSON.parse(fetchImpl.mock.calls[1]?.[1]?.body as string);

    expect(bodyA.sessionId).not.toBe(bodyB.sessionId);
  });
});
