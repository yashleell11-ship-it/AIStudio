import { describe, expect, it } from "vitest";
import {
  pageFromPointer,
  pageFromScrubRatio,
  parsePageInput,
  scrubPercent,
  scrubRatioForPage,
  scrubRatioFromPointer,
} from "./scrub";

describe("scrubRatioForPage", () => {
  it("anchors the first page at the start and the last at the end of the rail", () => {
    expect(scrubRatioForPage(1, 20)).toBe(0);
    expect(scrubRatioForPage(20, 20)).toBe(1);
    expect(scrubRatioForPage(11, 21)).toBeCloseTo(0.5);
  });

  it("clamps pages outside the chapter", () => {
    expect(scrubRatioForPage(0, 20)).toBe(0);
    expect(scrubRatioForPage(99, 20)).toBe(1);
  });

  it("reads full for a single-page chapter", () => {
    expect(scrubRatioForPage(1, 1)).toBe(1);
    expect(scrubPercent(1, 1)).toBe(100);
  });
});

describe("pageFromScrubRatio", () => {
  it("round-trips with scrubRatioForPage", () => {
    for (const page of [1, 2, 7, 19, 20]) {
      expect(pageFromScrubRatio(scrubRatioForPage(page, 20), 20)).toBe(page);
    }
  });

  it("reaches both ends of the chapter", () => {
    expect(pageFromScrubRatio(0, 20)).toBe(1);
    expect(pageFromScrubRatio(1, 20)).toBe(20);
  });

  it("clamps ratios and degenerate chapters", () => {
    expect(pageFromScrubRatio(-5, 20)).toBe(1);
    expect(pageFromScrubRatio(5, 20)).toBe(20);
    expect(pageFromScrubRatio(0.5, 0)).toBe(1);
    expect(pageFromScrubRatio(Number.NaN, 20)).toBe(1);
  });
});

describe("scrubRatioFromPointer", () => {
  const rect = { left: 100, width: 400 };

  it("measures the pointer against the track, not the viewport", () => {
    expect(scrubRatioFromPointer(100, rect, "ltr")).toBe(0);
    expect(scrubRatioFromPointer(300, rect, "ltr")).toBeCloseTo(0.5);
    expect(scrubRatioFromPointer(500, rect, "ltr")).toBe(1);
  });

  it("runs the rail backwards for a right-to-left chapter", () => {
    expect(scrubRatioFromPointer(100, rect, "rtl")).toBe(1);
    expect(scrubRatioFromPointer(500, rect, "rtl")).toBe(0);
  });

  it("clamps a drag that leaves the track", () => {
    expect(scrubRatioFromPointer(-50, rect, "ltr")).toBe(0);
    expect(scrubRatioFromPointer(9000, rect, "ltr")).toBe(1);
  });

  it("returns the start for an unmeasured track", () => {
    expect(scrubRatioFromPointer(50, { left: 0, width: 0 }, "ltr")).toBe(0);
  });
});

describe("pageFromPointer", () => {
  it("jumps to the page under the pointer", () => {
    const rect = { left: 0, width: 100 };
    expect(pageFromPointer(0, rect, 11, "ltr")).toBe(1);
    expect(pageFromPointer(50, rect, 11, "ltr")).toBe(6);
    expect(pageFromPointer(100, rect, 11, "ltr")).toBe(11);
    expect(pageFromPointer(0, rect, 11, "rtl")).toBe(11);
  });
});

describe("parsePageInput", () => {
  it("accepts whole page numbers and clamps them into the chapter", () => {
    expect(parsePageInput("7", 20)).toBe(7);
    expect(parsePageInput("  12 ", 20)).toBe(12);
    expect(parsePageInput("0", 20)).toBe(1);
    expect(parsePageInput("999", 20)).toBe(20);
  });

  it("rejects anything that is not a whole page number", () => {
    expect(parsePageInput("", 20)).toBeNull();
    expect(parsePageInput("abc", 20)).toBeNull();
    expect(parsePageInput("12.5", 20)).toBeNull();
    expect(parsePageInput("-3", 20)).toBeNull();
  });

  it("rejects every input for a chapter with no pages", () => {
    expect(parsePageInput("1", 0)).toBeNull();
  });
});
