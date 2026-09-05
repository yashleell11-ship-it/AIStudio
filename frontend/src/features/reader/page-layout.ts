import type { ReaderPage } from "./types";

export const DEFAULT_CONTAINER_WIDTH = 768;

/**
 * Height / width assumed for a page whose source reports no dimensions.
 *
 * MEASURED, not guessed: 487 first-hand page images from 44 live sources, of
 * which the 444 that come from connectors reporting no dimensions — the only
 * pages this constant is ever consulted for — have a GEOMETRIC MEAN h/w of
 * 3.375, rounded here to 3.4.
 *
 * The geometric mean rather than the median, because that population is
 * strongly bimodal: 51% of pages are page-format scans clustered at h/w ~1.4,
 * and 40% are webtoon strips from h/w 4 up to 23. There is no single value that
 * is right for both, so the one to pick is the one that minimises how many
 * TIMES wrong the estimate is, and the geometric mean is exactly that value.
 * Against the measured pages it takes the mean error from 4.2x to 3.1x, the
 * p90 from 12.1x to 5.8x, and the worst under-estimate — the expensive
 * direction, because too small an estimate makes the virtualizer mount many
 * rows where one belongs — from 15.5x to 7.1x. The old 3/2 was better only for
 * the short scans, and there it is now only wrong by ~2.4x for the one frame
 * before a real measurement replaces it.
 *
 * Every page whose connector DOES report dimensions skips this entirely — see
 * `exactPageHeight`. This is the honest prior for the rest, not a target.
 */
export const UNKNOWN_PAGE_ASPECT = 3.4;

export const MAX_CONTENT_WIDTH = 48 * 16;

export function resolveContainerWidth(scrollElement: HTMLElement | null): number {
  const measured = scrollElement?.clientWidth ?? 0;
  return measured > 0 ? measured : DEFAULT_CONTAINER_WIDTH;
}

/** The CSS width one page is laid out at: the reader column, times zoom. */
export function pageContentWidth(containerWidth: number, zoom: number): number {
  return Math.min(containerWidth, MAX_CONTENT_WIDTH) * zoom;
}

/**
 * The exact height a page will occupy, or `null` when the source did not say.
 *
 * Separate from {@link estimatePageHeight} because the difference matters to
 * the caller: this number is not an estimate to be averaged away once a few
 * rows have been measured, it is the answer. The strip's running average is for
 * pages nobody can size yet, and folding a known page into it would replace a
 * fact with a guess.
 */
export function exactPageHeight(
  page: ReaderPage,
  containerWidth: number,
  zoom: number,
): number | null {
  if (page.width == null || page.height == null) return null;
  if (!(page.width > 0) || !(page.height > 0)) return null;
  return (pageContentWidth(containerWidth, zoom) / page.width) * page.height;
}

export function estimatePageHeight(
  page: ReaderPage,
  containerWidth: number,
  zoom: number,
): number {
  return (
    exactPageHeight(page, containerWidth, zoom) ??
    pageContentWidth(containerWidth, zoom) * UNKNOWN_PAGE_ASPECT
  );
}

/**
 * CSS `aspect-ratio` for a page's placeholder box.
 *
 * Deliberately the same prior as {@link estimatePageHeight}: this string is
 * what the row actually measures as before the image decodes, so a placeholder
 * that disagreed with the estimate would hand the virtualizer a measurement
 * contradicting its own guess on every first paint.
 */
export function pageAspectRatio(width?: number | null, height?: number | null): string {
  if (width != null && height != null && width > 0 && height > 0) {
    return `${width} / ${height}`;
  }
  return `1 / ${UNKNOWN_PAGE_ASPECT}`;
}

/**
 * Sizing style for a page's container. The aspect ratio is only a placeholder
 * while the image loads; once loaded the image's intrinsic size must drive the
 * layout. Sources without page dimensions (e.g. AsuraScans webtoon strips up to
 * 900x16000) would otherwise be locked to the fallback box and clipped.
 */
export function pageContainerStyle(
  imageLoaded: boolean,
  width?: number | null,
  height?: number | null,
): { aspectRatio: string } | undefined {
  if (imageLoaded) {
    return undefined;
  }
  return { aspectRatio: pageAspectRatio(width, height) };
}

export function estimateScrollOffsetToPage(
  pages: ReaderPage[],
  pageNumber: number,
  containerWidth: number,
  zoom: number,
): number {
  const targetIndex = Math.max(0, Math.min(pageNumber - 1, pages.length - 1));
  let offset = 0;
  for (let index = 0; index < targetIndex; index += 1) {
    offset += estimatePageHeight(pages[index], containerWidth, zoom);
  }
  return offset;
}
