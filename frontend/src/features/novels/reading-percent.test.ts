import { describe, expect, it, vi } from "vitest";
import { createReadingPercent } from "./reading-percent";

describe("createReadingPercent", () => {
  it("starts at nothing read", () => {
    expect(createReadingPercent().get()).toBe(0);
  });

  it("reports whole percents", () => {
    const store = createReadingPercent();
    store.set(41.6);
    expect(store.get()).toBe(42);
  });

  it("clamps, so an overscrolled container cannot draw the hairline past the head", () => {
    const store = createReadingPercent();
    store.set(140);
    expect(store.get()).toBe(100);
    store.set(-12);
    expect(store.get()).toBe(0);
  });

  it("ignores a non-finite reading rather than printing NaN forever", () => {
    const store = createReadingPercent();
    const listener = vi.fn();
    store.subscribe(listener);

    store.set(Number.NaN);

    expect(store.get()).toBe(0);
    expect(listener).not.toHaveBeenCalled();
  });

  it("stays silent through the scroll frames that do not move the read-out", () => {
    const store = createReadingPercent();
    const listener = vi.fn();
    store.subscribe(listener);

    // A slow scroll across one percent: many frames, one number.
    for (let px = 0; px < 20; px += 1) store.set(41.2 + px * 0.01);

    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.get()).toBe(41);
  });

  it("tells every subscriber when the number moves", () => {
    const store = createReadingPercent();
    const readout = vi.fn();
    const hairline = vi.fn();
    store.subscribe(readout);
    store.subscribe(hairline);

    store.set(12);
    store.set(13);

    expect(readout).toHaveBeenCalledTimes(2);
    expect(hairline).toHaveBeenCalledTimes(2);
  });

  it("stops telling one that unsubscribed", () => {
    const store = createReadingPercent();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);

    unsubscribe();
    store.set(50);

    expect(listener).not.toHaveBeenCalled();
    expect(store.get()).toBe(50);
  });
});
