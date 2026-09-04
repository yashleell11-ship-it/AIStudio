import type { ContentMode } from "./mode";

/**
 * Destinations that only make sense in one mode.
 *
 * OCR search reads text recognised from chapter page IMAGES. A novel has no
 * images to recognise, so in Novels mode the screen could only ever be empty —
 * hiding the entry is more honest than showing a search box that can never
 * return anything.
 *
 * Keyed by href rather than by a flag on the nav item so `config/nav.ts` stays
 * a plain list of destinations, with no notion of a mode it predates.
 */
const MANGA_ONLY_HREFS = new Set(["/ocr"]);

/** Whether a nav destination belongs in this mode. */
export function isModeVisibleNavItem(
  href: string,
  mode: ContentMode,
  novelsEnabled: boolean,
): boolean {
  // With the flag off there is one mode and it is today's app: every
  // destination shows, exactly as it always has.
  if (!novelsEnabled) return true;
  if (mode === "manga") return true;
  return !MANGA_ONLY_HREFS.has(href);
}

/** Whether a route is manga-only, for the screen's own guard. */
export function isMangaOnlyRoute(href: string): boolean {
  return MANGA_ONLY_HREFS.has(href);
}
