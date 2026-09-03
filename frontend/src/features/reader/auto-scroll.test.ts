import { describe, expect, it } from "vitest";
import {
  autoScrollFrameDistance,
  autoScrollPxPerSecond,
  autoScrollReduce,
  clampAutoScrollSpeed,
  DEFAULT_AUTO_SCROLL_SPEED,
  INITIAL_AUTO_SCROLL_STATE,
  isExternalScroll,
  MAX_AUTO_SCROLL_SPEED,
  MAX_FRAME_DELTA_MS,
  MIN_AUTO_SCROLL_SPEED,
  type AutoScrollState,
} from "./auto-scroll";

describe("clampAutoScrollSpeed", () => {
  it("keeps values already in range", () => {
    expect(clampAutoScrollSpeed(5)).toBe(5);
    expect(clampAutoScrollSpeed(1)).toBe(1);
    expect(clampAutoScrollSpeed(10)).toBe(10);
  });

  it("clamps out-of-range values to the nearest bound", () => {
    expect(clampAutoScrollSpeed(0)).toBe(MIN_AUTO_SCROLL_SPEED);
    expect(clampAutoScrollSpeed(-5)).toBe(MIN_AUTO_SCROLL_SPEED);
    expect(clampAutoScrollSpeed(99)).toBe(MAX_AUTO_SCROLL_SPEED);
  });

  it("rounds fractional levels", () => {
    expect(clampAutoScrollSpeed(4.6)).toBe(5);
    expect(clampAutoScrollSpeed(4.4)).toBe(4);
  });

  it("falls back to the default for non-finite input", () => {
    expect(clampAutoScrollSpeed(NaN)).toBe(DEFAULT_AUTO_SCROLL_SPEED);
    expect(clampAutoScrollSpeed(Infinity)).toBe(DEFAULT_AUTO_SCROLL_SPEED);
  });
});

describe("autoScrollPxPerSecond", () => {
  it("is monotonically increasing across the speed range", () => {
    let previous = -Infinity;
    for (let level = MIN_AUTO_SCROLL_SPEED; level <= MAX_AUTO_SCROLL_SPEED; level += 1) {
      const rate = autoScrollPxPerSecond(level);
      expect(rate).toBeGreaterThan(previous);
      previous = rate;
    }
  });

  it("clamps an out-of-range speed before mapping it", () => {
    expect(autoScrollPxPerSecond(0)).toBe(autoScrollPxPerSecond(MIN_AUTO_SCROLL_SPEED));
    expect(autoScrollPxPerSecond(999)).toBe(autoScrollPxPerSecond(MAX_AUTO_SCROLL_SPEED));
  });
});

describe("autoScrollFrameDistance", () => {
  it("scales linearly with elapsed time (within one un-clamped frame gap)", () => {
    const rate = 100; // px/s
    expect(autoScrollFrameDistance(rate, 100)).toBeCloseTo(10);
    expect(autoScrollFrameDistance(rate, 50)).toBeCloseTo(5);
    expect(autoScrollFrameDistance(rate, 16.67)).toBeCloseTo(1.667, 2);
  });

  it("covers the same distance in the same wall-clock time at any frame rate", () => {
    const rate = 120; // px/s
    // 60fps: 60 frames of ~16.667ms each over one second.
    const sixty = Array.from({ length: 60 }, () => autoScrollFrameDistance(rate, 1000 / 60))
      .reduce((a, b) => a + b, 0);
    // 24fps: 24 frames of ~41.667ms each over the same second.
    const twentyFour = Array.from({ length: 24 }, () => autoScrollFrameDistance(rate, 1000 / 24))
      .reduce((a, b) => a + b, 0);
    expect(sixty).toBeCloseTo(120, 5);
    expect(twentyFour).toBeCloseTo(120, 5);
  });

  it("clamps a long frame gap instead of producing a jump", () => {
    const rate = 100;
    const long = autoScrollFrameDistance(rate, 5000);
    const clamped = autoScrollFrameDistance(rate, MAX_FRAME_DELTA_MS);
    expect(long).toBe(clamped);
  });

  it("is zero for a non-positive rate or elapsed time", () => {
    expect(autoScrollFrameDistance(0, 16)).toBe(0);
    expect(autoScrollFrameDistance(-10, 16)).toBe(0);
    expect(autoScrollFrameDistance(100, 0)).toBe(0);
    expect(autoScrollFrameDistance(100, -16)).toBe(0);
  });
});

describe("isExternalScroll", () => {
  it("treats a scroll landing exactly where the loop put it as self-caused", () => {
    expect(isExternalScroll(500, 500)).toBe(false);
  });

  it("tolerates sub-pixel rounding noise", () => {
    expect(isExternalScroll(500.3, 500)).toBe(false);
    expect(isExternalScroll(499.7, 500)).toBe(false);
  });

  it("flags a scroll that landed somewhere the loop did not expect", () => {
    expect(isExternalScroll(650, 500)).toBe(true);
    expect(isExternalScroll(400, 500)).toBe(true);
  });
});

describe("autoScrollReduce", () => {
  it("starts paused", () => {
    expect(INITIAL_AUTO_SCROLL_STATE).toEqual({ playing: false });
  });

  it("toggle flips play state either direction", () => {
    expect(autoScrollReduce(INITIAL_AUTO_SCROLL_STATE, { type: "toggle" })).toEqual({
      playing: true,
    });
    const playing: AutoScrollState = { playing: true };
    expect(autoScrollReduce(playing, { type: "toggle" })).toEqual({ playing: false });
  });

  it("play is idempotent while already playing", () => {
    const playing: AutoScrollState = { playing: true };
    expect(autoScrollReduce(playing, { type: "play" })).toBe(playing);
  });

  it("play starts playback from paused", () => {
    expect(autoScrollReduce(INITIAL_AUTO_SCROLL_STATE, { type: "play" })).toEqual({
      playing: true,
    });
  });

  it("pause, interaction and end-of-chapter all stop playback", () => {
    const playing: AutoScrollState = { playing: true };
    expect(autoScrollReduce(playing, { type: "pause" })).toEqual({ playing: false });
    expect(autoScrollReduce(playing, { type: "interaction" })).toEqual({ playing: false });
    expect(autoScrollReduce(playing, { type: "end-of-chapter" })).toEqual({ playing: false });
  });

  it("pause-like events are no-ops while already paused (stable reference)", () => {
    expect(autoScrollReduce(INITIAL_AUTO_SCROLL_STATE, { type: "pause" })).toBe(
      INITIAL_AUTO_SCROLL_STATE,
    );
    expect(autoScrollReduce(INITIAL_AUTO_SCROLL_STATE, { type: "interaction" })).toBe(
      INITIAL_AUTO_SCROLL_STATE,
    );
    expect(autoScrollReduce(INITIAL_AUTO_SCROLL_STATE, { type: "end-of-chapter" })).toBe(
      INITIAL_AUTO_SCROLL_STATE,
    );
  });

  it("a manual scroll or a tap pauses it immediately, from any playing state", () => {
    let state = autoScrollReduce(INITIAL_AUTO_SCROLL_STATE, { type: "play" });
    expect(state.playing).toBe(true);
    state = autoScrollReduce(state, { type: "interaction" });
    expect(state.playing).toBe(false);
  });
});
