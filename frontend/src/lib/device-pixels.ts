/**
 * How many DEVICE pixels a CSS box is worth asking an image proxy for.
 *
 * One rule, shared by the cover proxy (`cover-url.ts`) and the reader page
 * proxy (`features/reader/page-url.ts`), because both routes take the same
 * `?w=` in the same units and a second copy of the clamp would drift from the
 * first the moment either moved.
 */

/**
 * Device pixels per CSS pixel that an image is ever requested at.
 *
 * Past 3x the extra rows are not resolvable on the panels that report them, and
 * both server ladders top out anyway: 4x on a phone asks for the original.
 */
const MAX_PIXEL_RATIO = 3;

/**
 * What is assumed when there is no `window`.
 *
 * Neither covers nor reader pages are ever server-rendered with rows in hand —
 * every view gets them from react-query in the browser, so the server renders
 * skeletons and the first markup that carries an image URL is produced on the
 * client with the real numbers available. This constant exists so the builders
 * stay pure functions under Node (and vitest), not because it is ever hydrated.
 *
 * It is also why the ratio is read synchronously during render rather than
 * settled in an effect: an effect that upgraded a placeholder ratio after mount
 * would rewrite every image URL on the page and fetch every image a second time.
 */
const SSR_PIXEL_RATIO = 2;

/** Device pixels per CSS pixel, clamped to what is worth rendering at. */
export function imagePixelRatio(): number {
  if (typeof window === "undefined") {
    return SSR_PIXEL_RATIO;
  }
  const ratio = window.devicePixelRatio;
  return Number.isFinite(ratio) && ratio > 0 ? Math.min(ratio, MAX_PIXEL_RATIO) : 1;
}
