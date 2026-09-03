import type { ChapterId } from "@/types/api";

export type { ChapterId };

export interface ReaderPage {
  id: string;
  number: number;
  imageUrl: string;
  width: number | null;
  height: number | null;
}

/**
 * How pages are laid out in the viewport. `continuous` is the long-strip scroll
 * the reader has always used; the paged modes show one screenful at a time.
 */
export type ReadingMode = "single" | "double" | "continuous";

/** How a page is sized inside the viewport before the zoom multiplier. */
export type FitMode = "width" | "height" | "original";

/**
 * Manga reads right-to-left; webtoons and western comics read left-to-right.
 * No source reports this, so it is a reader-side preference per series.
 */
export type ReadingDirection = "ltr" | "rtl";

/**
 * A chapter ready to render, built from `GET /reader/chapter/manifest`
 * (`manifestToChapterContent`). Source-native: there is only one content path
 * now — pages stream from the source proxy, and the service worker transparently
 * serves the same URLs from Cache Storage when the chapter is downloaded.
 */
export interface ReaderChapterContent {
  sourceId: string;
  seriesKey: string;
  chapterKey: string;
  chapterNumber: number | null;
  title: string;
  pageCount: number;
  pages: ReaderPage[];
  previousChapterKey: string | null;
  nextChapterKey: string | null;
  seriesTitle?: string | null;
}

export interface ReaderNavigation {
  backHref: string;
  previousChapterHref: string | null;
  nextChapterHref: string | null;
}
