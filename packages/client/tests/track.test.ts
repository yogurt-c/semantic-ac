import { describe, expect, it, vi } from "vitest";
import { trackSearch } from "../src/track";

function makeResponse(status: number): Response {
  return { ok: status >= 200 && status < 300, status } as Response;
}

describe("trackSearch", () => {
  it("posts prefix, selected, and action to {baseUrl}/track", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(makeResponse(202));

    await trackSearch(
      { baseUrl: "https://api.example.com", fetchImpl },
      { prefix: "노트", selected: "노트북", action: "suggestion_click" },
    );

    expect(fetchImpl).toHaveBeenCalledWith(
      "https://api.example.com/track",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prefix: "노트", selected: "노트북", action: "suggestion_click" }),
      }),
    );
  });

  it("resolves without inspecting the response body on 202", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(makeResponse(202));

    await expect(
      trackSearch(
        { baseUrl: "https://api.example.com", fetchImpl },
        { prefix: "노트", selected: "노트북", action: "final_search" },
      ),
    ).resolves.toBeUndefined();
  });

  it("throws when the server responds with a non-2xx status", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(makeResponse(500));

    await expect(
      trackSearch(
        { baseUrl: "https://api.example.com", fetchImpl },
        { prefix: "노트", selected: "노트북", action: "suggestion_click" },
      ),
    ).rejects.toThrow();
  });

  it("propagates network errors instead of swallowing them", async () => {
    const networkError = new Error("network down");
    const fetchImpl = vi.fn().mockRejectedValue(networkError);

    await expect(
      trackSearch(
        { baseUrl: "https://api.example.com", fetchImpl },
        { prefix: "노트", selected: "노트북", action: "suggestion_click" },
      ),
    ).rejects.toThrow("network down");
  });
});
