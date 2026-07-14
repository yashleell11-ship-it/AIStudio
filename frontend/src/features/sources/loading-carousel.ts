/**
 * Pure helpers for the source-browse loading carousel. Kept free of React and
 * the DOM so the slide/rotation maths can be unit-tested in the node test env.
 */

/** How many covers are shown side-by-side in a single carousel frame. */
export const COVERS_PER_SLIDE = 3;

/**
 * Rotating tips shown while a source is opening and the viewer has no reading
 * history to display. Decorative filler only.
 */
export const LOADING_TIPS: readonly string[] = [
  "Tip: press / anywhere to jump straight to the source search box.",
  "Tip: pick a browse mode (Latest, Popular…) to reshuffle the catalog.",
  "Tip: tap any genre chip on a series to filter this source by it.",
  "Tip: your reading progress syncs across every device you sign in on.",
] as const;

/**
 * Split a flat list into fixed-size slides of `perSlide` items each. The final
 * slide keeps whatever remainder is left (it is not padded). An empty input
 * yields no slides.
 */
export function buildCarouselSlides<T>(
  items: readonly T[],
  perSlide: number = COVERS_PER_SLIDE,
): T[][] {
  if (perSlide < 1) {
    throw new Error("perSlide must be at least 1");
  }
  const slides: T[][] = [];
  for (let index = 0; index < items.length; index += perSlide) {
    slides.push(items.slice(index, index + perSlide));
  }
  return slides;
}

/**
 * The next slide index, wrapping back to 0 after the last slide. Returns 0 when
 * there are no slides so callers never index out of bounds.
 */
export function nextSlideIndex(current: number, slideCount: number): number {
  if (slideCount <= 0) {
    return 0;
  }
  return (current + 1) % slideCount;
}

/**
 * A stable HSL wash colour derived from a source id, used as a faint background
 * tint on the loading state so each source feels a little branded without any
 * per-source asset. Deterministic: the same id always yields the same hue.
 */
export function sourceHue(sourceId: string): number {
  let hash = 0;
  for (let index = 0; index < sourceId.length; index += 1) {
    hash = (hash * 31 + sourceId.charCodeAt(index)) % 360;
  }
  return Math.abs(hash);
}
