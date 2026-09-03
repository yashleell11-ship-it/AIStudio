import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHoverIntent, HOVER_PREFETCH_DELAY_MS } from "./hover-intent";

describe("createHoverIntent", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("runs for the row the pointer settles on", () => {
    const run = vi.fn();
    const intent = createHoverIntent(run);
    intent.enter("ch-7");
    vi.advanceTimersByTime(HOVER_PREFETCH_DELAY_MS);
    expect(run).toHaveBeenCalledExactlyOnceWith("ch-7");
  });

  it("costs nothing to sweep the pointer down a long list", () => {
    // The regression: one mouseenter per row fired one request per row, which
    // is what emptied the /sources rate-limit bucket in a single gesture.
    const run = vi.fn();
    const intent = createHoverIntent(run);
    for (let i = 0; i < 60; i += 1) {
      intent.enter(`ch-${i}`);
      vi.advanceTimersByTime(10);
    }
    expect(run).not.toHaveBeenCalled();

    vi.advanceTimersByTime(HOVER_PREFETCH_DELAY_MS);
    expect(run).toHaveBeenCalledExactlyOnceWith("ch-59");
  });

  it("cancels when the pointer leaves before the delay", () => {
    const run = vi.fn();
    const intent = createHoverIntent(run);
    intent.enter("ch-7");
    vi.advanceTimersByTime(HOVER_PREFETCH_DELAY_MS - 1);
    intent.leave();
    vi.advanceTimersByTime(1_000);
    expect(run).not.toHaveBeenCalled();
  });

  it("does not fire after dispose", () => {
    const run = vi.fn();
    const intent = createHoverIntent(run);
    intent.enter("ch-7");
    intent.dispose();
    vi.advanceTimersByTime(1_000);
    expect(run).not.toHaveBeenCalled();
  });
});
