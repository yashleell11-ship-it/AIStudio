/**
 * Typography controls for the novel reader: size, leading, measure and face.
 *
 * **System stacks only.** The site is self-hosted behind a strict CSP and
 * downloads no webfonts, so "serif" and "sans" are families the reader's OS
 * already has. Both stacks lead with the best long-form faces each platform
 * ships and fall back through the usual suspects, so the choice is a real
 * change of face everywhere rather than "Georgia or nothing".
 *
 * The ranges are clamped rather than free: a 9px measure of 200 characters is
 * not a preference, it is a broken page, and these values are persisted so a
 * bad one would follow the reader around.
 */

export type NovelFontFamily = "serif" | "sans";

/**
 * Long-form serif stack. Iowan Old Style (macOS/iOS, Apple Books' own face)
 * and Charter (also on Android as its metric sibling) are the two best
 * reading faces that ship on a device; Georgia is the near-universal floor.
 */
export const NOVEL_SERIF_STACK =
  '"Iowan Old Style", "Palatino Linotype", Palatino, Charter, "Bitstream Charter", Georgia, Cambria, "Times New Roman", serif';

/** The platform UI face, which is what a sans reader actually wants here. */
export const NOVEL_SANS_STACK =
  'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif';

export function novelFontStack(family: NovelFontFamily): string {
  return family === "sans" ? NOVEL_SANS_STACK : NOVEL_SERIF_STACK;
}

/** Body size in px. */
export const MIN_FONT_SIZE = 15;
export const MAX_FONT_SIZE = 26;
export const FONT_SIZE_STEP = 1;
export const DEFAULT_FONT_SIZE = 19;

/** Unitless line-height multiplier. Generous by default — this is prose. */
export const MIN_LINE_HEIGHT = 1.4;
export const MAX_LINE_HEIGHT = 2.1;
export const LINE_HEIGHT_STEP = 0.05;
export const DEFAULT_LINE_HEIGHT = 1.75;

/**
 * Column width in `ch`, which tracks the chosen face's own character width —
 * so the measure stays a measure when the size changes, instead of a fixed
 * pixel column that goes narrow-and-cramped at 26px.
 */
export const MIN_MEASURE = 48;
export const MAX_MEASURE = 88;
export const MEASURE_STEP = 2;
/** The comfortable default: ~68 characters a line. */
export const DEFAULT_MEASURE = 68;

function clampTo(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

export function clampFontSize(value: number): number {
  return Math.round(clampTo(value, MIN_FONT_SIZE, MAX_FONT_SIZE, DEFAULT_FONT_SIZE));
}

export function clampLineHeight(value: number): number {
  const clamped = clampTo(value, MIN_LINE_HEIGHT, MAX_LINE_HEIGHT, DEFAULT_LINE_HEIGHT);
  // Two decimals: the step is 0.05 and float arithmetic on it drifts.
  return Math.round(clamped * 100) / 100;
}

export function clampMeasure(value: number): number {
  return Math.round(clampTo(value, MIN_MEASURE, MAX_MEASURE, DEFAULT_MEASURE));
}

export function isNovelFontFamily(value: unknown): value is NovelFontFamily {
  return value === "serif" || value === "sans";
}

/** Step a value and re-clamp, for the +/- buttons and the keyboard bindings. */
export function stepFontSize(current: number, steps: number): number {
  return clampFontSize(current + steps * FONT_SIZE_STEP);
}

export function stepLineHeight(current: number, steps: number): number {
  return clampLineHeight(current + steps * LINE_HEIGHT_STEP);
}

export function stepMeasure(current: number, steps: number): number {
  return clampMeasure(current + steps * MEASURE_STEP);
}
