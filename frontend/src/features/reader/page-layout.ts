import type { ReaderPage } from "./types";

export const DEFAULT_CONTAINER_WIDTH = 768;

const DEFAULT_ASPECT_RATIO = 3 / 2;
const MAX_CONTENT_WIDTH = 48 * 16;

export function resolveContainerWidth(scrollElement: HTMLElement | null): number {
  const measured = scrollElement?.clientWidth ?? 0;
  return measured > 0 ? measured : DEFAULT_CONTAINER_WIDTH;
}

export function estimatePageHeight(
  page: ReaderPage,
  containerWidth: number,
  zoom: number,
): number {
  const contentWidth = Math.min(containerWidth, MAX_CONTENT_WIDTH) * zoom;
  if (page.width != null && page.height != null && page.width > 0) {
    return (contentWidth / page.width) * page.height;
  }
  return contentWidth * DEFAULT_ASPECT_RATIO;
}

export function pageAspectRatio(width?: number | null, height?: number | null): string {
  if (width != null && height != null && width > 0 && height > 0) {
    return `${width} / ${height}`;
  }
  return "2 / 3";
}

/**
 * Sizing style for a page's container. The aspect ratio is only a placeholder
 * while the image loads; once loaded the image's intrinsic size must drive the
 * layout. Sources without page dimensions (e.g. AsuraScans webtoon strips up to
 * 900x16000) would otherwise be locked to the 2/3 fallback box and clipped.
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
