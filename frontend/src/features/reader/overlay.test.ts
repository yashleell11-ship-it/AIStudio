import { describe, expect, it } from "vitest";
import { clampDimmer, clampWarmth, MAX_DIMMER, MAX_WARMTH } from "./overlay";

describe("clampDimmer", () => {
  it("keeps in-range values", () => {
    expect(clampDimmer(0)).toBe(0);
    expect(clampDimmer(0.5)).toBe(0.5);
  });

  it("never reaches fully opaque, even when asked for 1 or more", () => {
    expect(clampDimmer(1)).toBe(MAX_DIMMER);
    expect(clampDimmer(1)).toBeLessThan(1);
    expect(clampDimmer(999)).toBe(MAX_DIMMER);
  });

  it("floors negative input at zero", () => {
    expect(clampDimmer(-1)).toBe(0);
  });

  it("treats non-finite input as off", () => {
    expect(clampDimmer(NaN)).toBe(0);
    expect(clampDimmer(Infinity)).toBe(0);
  });
});

describe("clampWarmth", () => {
  it("keeps in-range values", () => {
    expect(clampWarmth(0)).toBe(0);
    expect(clampWarmth(0.3)).toBe(0.3);
  });

  it("caps below fully saturated", () => {
    expect(clampWarmth(1)).toBe(MAX_WARMTH);
    expect(clampWarmth(1)).toBeLessThan(1);
  });

  it("floors negative input at zero and handles non-finite input", () => {
    expect(clampWarmth(-1)).toBe(0);
    expect(clampWarmth(NaN)).toBe(0);
  });
});
