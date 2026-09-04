import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  clampFontSize,
  clampLineHeight,
  clampMeasure,
  DEFAULT_FONT_SIZE,
  DEFAULT_LINE_HEIGHT,
  DEFAULT_MEASURE,
  isNovelFontFamily,
  MAX_FONT_SIZE,
  MAX_LINE_HEIGHT,
  MAX_MEASURE,
  MIN_FONT_SIZE,
  MIN_LINE_HEIGHT,
  MIN_MEASURE,
  NOVEL_SANS_STACK,
  NOVEL_SERIF_STACK,
  novelFontStack,
  stepFontSize,
  stepLineHeight,
  stepMeasure,
} from "./typography";

describe("font stacks", () => {
  it("names only faces a device already has — the CSP downloads no webfonts", () => {
    for (const stack of [NOVEL_SERIF_STACK, NOVEL_SANS_STACK]) {
      expect(stack).not.toMatch(/url\(|https?:|@import/i);
    }
  });

  it("ends each stack in a generic family, so there is always something to render", () => {
    expect(NOVEL_SERIF_STACK.trim().endsWith("serif")).toBe(true);
    expect(NOVEL_SANS_STACK.trim().endsWith("sans-serif")).toBe(true);
  });

  it("switches face on the toggle", () => {
    expect(novelFontStack("serif")).toBe(NOVEL_SERIF_STACK);
    expect(novelFontStack("sans")).toBe(NOVEL_SANS_STACK);
  });
});

describe("clamps", () => {
  it("holds font size inside a readable range", () => {
    expect(clampFontSize(19)).toBe(19);
    expect(clampFontSize(2)).toBe(MIN_FONT_SIZE);
    expect(clampFontSize(400)).toBe(MAX_FONT_SIZE);
    expect(clampFontSize(Number.NaN)).toBe(DEFAULT_FONT_SIZE);
    expect(clampFontSize(18.6)).toBe(19);
  });

  it("holds line height inside a readable range, without float drift", () => {
    expect(clampLineHeight(1.75)).toBe(1.75);
    expect(clampLineHeight(0.2)).toBe(MIN_LINE_HEIGHT);
    expect(clampLineHeight(9)).toBe(MAX_LINE_HEIGHT);
    expect(clampLineHeight(Number.NaN)).toBe(DEFAULT_LINE_HEIGHT);
    expect(clampLineHeight(1.7000000000000002)).toBe(1.7);
  });

  it("holds the measure inside a readable column", () => {
    expect(clampMeasure(68)).toBe(68);
    expect(clampMeasure(5)).toBe(MIN_MEASURE);
    expect(clampMeasure(300)).toBe(MAX_MEASURE);
    expect(clampMeasure(Number.NaN)).toBe(DEFAULT_MEASURE);
  });
});

describe("stepping", () => {
  it("moves by one step and re-clamps at the ends", () => {
    expect(stepFontSize(19, 1)).toBe(20);
    expect(stepFontSize(19, -1)).toBe(18);
    expect(stepFontSize(MAX_FONT_SIZE, 5)).toBe(MAX_FONT_SIZE);
    expect(stepFontSize(MIN_FONT_SIZE, -5)).toBe(MIN_FONT_SIZE);
  });

  it("steps leading in 0.05 without accumulating float error", () => {
    let value = DEFAULT_LINE_HEIGHT;
    for (let i = 0; i < 4; i += 1) value = stepLineHeight(value, 1);
    expect(value).toBe(1.95);
    expect(stepLineHeight(MAX_LINE_HEIGHT, 3)).toBe(MAX_LINE_HEIGHT);
  });

  it("steps the measure in whole characters", () => {
    expect(stepMeasure(68, 1)).toBe(70);
    expect(stepMeasure(68, -1)).toBe(66);
    expect(stepMeasure(MIN_MEASURE, -4)).toBe(MIN_MEASURE);
  });
});

describe("isNovelFontFamily", () => {
  it("accepts only the two faces on offer", () => {
    expect(isNovelFontFamily("serif")).toBe(true);
    expect(isNovelFontFamily("sans")).toBe(true);
    expect(isNovelFontFamily("cursive")).toBe(false);
    expect(isNovelFontFamily(null)).toBe(false);
  });
});

/**
 * `--font-book` in globals.css is the same stack as `NOVEL_SERIF_STACK`, so the
 * shelf and the front matter (which use the Tailwind `font-book` utility) and
 * the reader (which applies the stack inline, because the reader's face is a
 * per-series preference) cannot drift onto different serifs.
 */
describe("the CSS token and the TS stack are one stack", () => {
  const CSS = readFileSync(
    path.resolve(__dirname, "../../app/globals.css"),
    "utf8",
  );

  it("declares --font-book identically to NOVEL_SERIF_STACK", () => {
    const match = /--font-book:\s*([^;]+);/.exec(CSS);
    expect(match, "--font-book is not declared in globals.css").not.toBeNull();
    expect(match![1].trim()).toBe(NOVEL_SERIF_STACK);
  });
});
