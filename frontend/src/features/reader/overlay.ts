/**
 * Brightness (dimmer) and warmth (sepia) overlays for night reading.
 *
 * The browser cannot touch the device's actual backlight, so this fakes it in
 * page: a dark scrim over the pages for "brightness", and a warm amber wash
 * for "warmth", each a continuous 0..1 slider persisted per profile
 * (`reader-settings.ts`). Both are rendered as CSS opacity on fixed overlay
 * layers — see `ChapterReader` — so this module only owns the numbers.
 */

/**
 * The dimmer must never be able to black out the reader entirely — a user
 * who drags it all the way could otherwise "brick" the page with no visible
 * control left to undo it. Capping short of full opacity guarantees the
 * chrome (rendered above the overlay) stays legible enough to find and drag
 * the slider back down.
 */
export const MAX_DIMMER = 0.92;

/** Warmth is a tint, not a blackout, but is still capped well short of solid. */
export const MAX_WARMTH = 0.7;

export function clampDimmer(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(MAX_DIMMER, Math.max(0, value));
}

export function clampWarmth(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(MAX_WARMTH, Math.max(0, value));
}
