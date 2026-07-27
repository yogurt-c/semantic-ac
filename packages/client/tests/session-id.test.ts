import { afterEach, describe, expect, it } from "vitest";
import { createSessionId } from "../src/session-id";

describe("createSessionId", () => {
  afterEach(() => {
    delete (globalThis as { crypto?: Crypto }).crypto;
  });

  it("returns a non-empty string", () => {
    expect(createSessionId().length).toBeGreaterThan(0);
  });

  it("returns a different id on each call", () => {
    expect(createSessionId()).not.toBe(createSessionId());
  });

  it("uses crypto.randomUUID when available", () => {
    (globalThis as { crypto?: Crypto }).crypto = {
      randomUUID: () => "fixed-uuid",
    } as unknown as Crypto;

    expect(createSessionId()).toBe("fixed-uuid");
  });

  it("falls back to a manual id when crypto.randomUUID is unavailable", () => {
    (globalThis as { crypto?: Crypto }).crypto = {} as Crypto;

    expect(createSessionId().length).toBeGreaterThan(0);
  });
});
