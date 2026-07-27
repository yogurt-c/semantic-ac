import { describe, expect, it } from "vitest";
import { PrefixCache } from "../src/cache";

describe("PrefixCache", () => {
  it("returns undefined for a prefix that was never set", () => {
    const cache = new PrefixCache<string[]>();

    expect(cache.get("노트")).toBeUndefined();
    expect(cache.has("노트")).toBe(false);
  });

  it("returns the cached value for a previously set prefix", () => {
    const cache = new PrefixCache<string[]>();

    cache.set("노트", ["노트북", "노트북 추천"]);

    expect(cache.get("노트")).toEqual(["노트북", "노트북 추천"]);
    expect(cache.has("노트")).toBe(true);
  });

  it("overwrites the value when the same prefix is set again", () => {
    const cache = new PrefixCache<string[]>();

    cache.set("노트", ["노트북"]);
    cache.set("노트", ["노트북 추천"]);

    expect(cache.get("노트")).toEqual(["노트북 추천"]);
  });

  it("clears all entries", () => {
    const cache = new PrefixCache<string[]>();

    cache.set("노트", ["노트북"]);
    cache.clear();

    expect(cache.get("노트")).toBeUndefined();
    expect(cache.has("노트")).toBe(false);
  });

  it("evicts the oldest entry once maxEntries is exceeded", () => {
    const cache = new PrefixCache<string[]>(2);

    cache.set("a", ["A"]);
    cache.set("b", ["B"]);
    cache.set("c", ["C"]);

    expect(cache.has("a")).toBe(false);
    expect(cache.has("b")).toBe(true);
    expect(cache.has("c")).toBe(true);
  });

  it("never stores entries when maxEntries is zero", () => {
    const cache = new PrefixCache<string[]>(0);

    cache.set("a", ["A"]);

    expect(cache.has("a")).toBe(false);
    expect(cache.get("a")).toBeUndefined();
  });

  it("never stores entries when maxEntries is negative", () => {
    const cache = new PrefixCache<string[]>(-1);

    cache.set("a", ["A"]);

    expect(cache.has("a")).toBe(false);
    expect(cache.get("a")).toBeUndefined();
  });

  it("does not evict when overwriting an existing key at capacity", () => {
    const cache = new PrefixCache<string[]>(2);

    cache.set("a", ["A"]);
    cache.set("b", ["B"]);
    cache.set("a", ["A2"]);

    expect(cache.has("a")).toBe(true);
    expect(cache.has("b")).toBe(true);
    expect(cache.get("a")).toEqual(["A2"]);
  });
});
