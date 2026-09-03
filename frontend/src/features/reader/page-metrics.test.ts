import { describe, expect, it } from "vitest";
import {
  EMPTY_HEIGHT_SAMPLES,
  estimateFromSamples,
  recordHeight,
  stripHeight,
  stripOffsets,
} from "./page-metrics";

describe("stripOffsets / stripHeight — zero-gap layout math", () => {
  const heights = [1000, 1400, 900, 1600];

  it("stacks pages flush: each offset is the exact prefix sum of heights", () => {
    expect(stripOffsets(heights, 0)).toEqual([0, 1000, 2400, 3300]);
  });

  it("flush total height is the plain sum — no seam, no trailing gap", () => {
    expect(stripHeight(heights, 0)).toBe(4900);
  });

  it("the last page's bottom edge equals the total height (no gap beneath it)", () => {
    const offsets = stripOffsets(heights, 0);
    const lastBottom = offsets[offsets.length - 1] + heights[heights.length - 1];
    expect(lastBottom).toBe(stripHeight(heights, 0));
  });

  it("a gap is inserted only between pages, never before the first or after the last", () => {
    expect(stripOffsets(heights, 8)).toEqual([0, 1008, 2416, 3324]);
    // 4900 pages + 8 * 3 gaps
    expect(stripHeight(heights, 8)).toBe(4924);
  });

  it("is inert for an empty strip", () => {
    expect(stripOffsets([], 0)).toEqual([]);
    expect(stripHeight([], 8)).toBe(0);
  });

  it("clamps negative heights and gaps to zero", () => {
    expect(stripHeight([100, -50, 100], -4)).toBe(200);
  });
});

describe("measured-height feedback", () => {
  it("falls back to the fixed-aspect guess until a page is measured", () => {
    expect(estimateFromSamples(EMPTY_HEIGHT_SAMPLES, 1152)).toBe(1152);
  });

  it("averages measured heights once samples exist", () => {
    let samples = EMPTY_HEIGHT_SAMPLES;
    samples = recordHeight(samples, undefined, 2000);
    samples = recordHeight(samples, undefined, 3000);
    expect(estimateFromSamples(samples, 1152)).toBe(2500);
  });

  it("re-measuring a page replaces its old sample instead of double-counting", () => {
    let samples = EMPTY_HEIGHT_SAMPLES;
    samples = recordHeight(samples, undefined, 2000);
    samples = recordHeight(samples, 2000, 2600); // same page, taller after reflow
    expect(samples).toEqual({ total: 2600, count: 1 });
    expect(estimateFromSamples(samples, 1152)).toBe(2600);
  });

  it("ignores non-positive measurements", () => {
    const samples = recordHeight(EMPTY_HEIGHT_SAMPLES, undefined, 0);
    expect(samples).toBe(EMPTY_HEIGHT_SAMPLES);
  });
});
