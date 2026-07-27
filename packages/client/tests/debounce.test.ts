import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { debounce } from "../src/debounce";

describe("debounce", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not call the function before the wait time elapses", () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 150);

    debounced("a");
    vi.advanceTimersByTime(149);

    expect(fn).not.toHaveBeenCalled();
  });

  it("calls the function once the wait time elapses", () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 150);

    debounced("a");
    vi.advanceTimersByTime(150);

    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("a");
  });

  it("resets the timer on repeated calls within the wait window", () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 150);

    debounced("a");
    vi.advanceTimersByTime(100);
    debounced("b");
    vi.advanceTimersByTime(100);

    expect(fn).not.toHaveBeenCalled();

    vi.advanceTimersByTime(50);

    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("b");
  });

  it("only invokes the underlying function once per settled burst", () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 150);

    debounced("a");
    debounced("b");
    debounced("c");
    vi.advanceTimersByTime(150);

    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("c");
  });

  it("cancels a pending call when cancel() is invoked", () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 150);

    debounced("a");
    debounced.cancel();
    vi.advanceTimersByTime(150);

    expect(fn).not.toHaveBeenCalled();
  });
});
