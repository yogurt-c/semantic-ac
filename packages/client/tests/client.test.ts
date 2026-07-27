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

  it("delegates trackSearch to POST {baseUrl}/track", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, status: 202 } as Response);
    const client = new SemanticAutocompleteClient({ baseUrl: "https://api.example.com", fetchImpl });

    await client.trackSearch("노트", "노트북", "suggestion_click");

    expect(fetchImpl).toHaveBeenCalledWith(
      "https://api.example.com/track",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prefix: "노트", selected: "노트북", action: "suggestion_click" }),
      }),
    );
  });
});
