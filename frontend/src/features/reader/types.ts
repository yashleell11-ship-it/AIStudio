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

export interface ReaderChapterContent {
  id: string;
  seriesId: string;
  title: string;
  pageCount: number;
  pages: ReaderPage[];
  previousChapterId: string | null;
  nextChapterId: string | null;
  seriesTitle?: string | null;
  mode: "local" | "remote";
  sourceId?: string | null;
}

export interface ReaderNavigation {
  backHref: string;
  previousChapterHref: string | null;
  nextChapterHref: string | null;
}
