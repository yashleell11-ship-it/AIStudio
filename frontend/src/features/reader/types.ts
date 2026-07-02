export interface ReaderPage {
  id: string;
  number: number;
  imageUrl: string;
  width: number | null;
  height: number | null;
}

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
