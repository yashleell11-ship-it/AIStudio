import { env } from "@/config/env";
import { http, sourceChapterQuery } from "@/services/http";
import type { ChapterId, SeriesId } from "@/types/api";
import type { ReaderChapterContent, ReaderPage } from "./types";

export interface Bookmark {
  id: number;
  source_id: string;
  series_key: string;
  chapter_key: string;
  page: number;
  note: string | null;
  created_at: string | null;
}

/** `GET /reader/chapter/manifest` (backend `ReaderService.manifest`). */
export interface ChapterManifest {
  source_id: string;
  series_key: string;
  chapter_key: string;
  chapter_number: number | null;
  page_count: number;
  pages: Array<{ number: number; url: string }>;
  /** Adjacent chapter keys, or null at the ends. */
  prev: string | null;
  next: string | null;
}

/** `POST /reader/progress` push / stored row (progress-service `_serialize`). */
export interface ReadingProgress {
  id: number;
  source_id: string;
  series_key: string;
  chapter_key: string;
  chapter_number: number | null;
  last_page: number;
  page_count: number;
  scroll_offset_px: number;
  is_completed: boolean;
  started_at: string | null;
  last_read_at: string | null;
  completed_at: string | null;
  time_spent_seconds: number;
  /** Only on the `POST /reader/progress` response: did the stored row advance? */
  advanced?: boolean;
}

export interface ProgressPush {
  source_id: string;
  series_key: string;
  chapter_key: string;
  chapter_number?: number | null;
  last_page: number;
  page_count?: number;
  scroll_offset_px?: number;
  is_completed?: boolean;
  time_spent_seconds?: number;
}

function absoluteImageUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  return `${env.apiUrl}${url.startsWith("/") ? "" : "/"}${url}`;
}

/** Build a renderable chapter from a manifest. The sole content builder. */
export function manifestToChapterContent(
  manifest: ChapterManifest,
): ReaderChapterContent {
  const title =
    manifest.chapter_number != null
      ? `Chapter ${manifest.chapter_number}`
      : "Chapter";
  return {
    sourceId: manifest.source_id,
    seriesKey: manifest.series_key,
    chapterKey: manifest.chapter_key,
    chapterNumber: manifest.chapter_number,
    title,
    pageCount: manifest.page_count,
    previousChapterKey: manifest.prev,
    nextChapterKey: manifest.next,
    pages: manifest.pages.map(
      (page): ReaderPage => ({
        id: `${manifest.chapter_key}:${page.number}`,
        number: page.number,
        imageUrl: absoluteImageUrl(page.url),
        width: null,
        height: null,
      }),
    ),
  };
}

function toPush(ref: ChapterId, rest: Omit<ProgressPush, "source_id" | "series_key" | "chapter_key">): ProgressPush {
  return {
    source_id: ref.sourceId,
    series_key: ref.seriesKey,
    chapter_key: ref.chapterKey,
    ...rest,
  };
}

export const readerApi = {
  manifest: (ref: ChapterId) =>
    http.get<ChapterManifest>("/reader/chapter/manifest", {
      query: sourceChapterQuery(ref),
    }),

  saveProgress: (ref: ChapterId, body: Omit<ProgressPush, "source_id" | "series_key" | "chapter_key">) =>
    http.post<ReadingProgress>("/reader/progress", toPush(ref, body)),

  /** Offline-sync flush of queued progress pushes. */
  saveProgressBatch: (pushes: ProgressPush[]) =>
    http.post<{ saved: number; advanced: number; items: ReadingProgress[] }>(
      "/reader/progress/batch",
      pushes,
    ),

  seriesProgress: (ref: SeriesId) =>
    http.get<ReadingProgress[]>("/reader/progress/series", {
      query: sourceChapterQuery(ref),
    }),

  addBookmark: (ref: ChapterId, page: number, note?: string) =>
    http.post<Bookmark>("/reader/bookmark", {
      source_id: ref.sourceId,
      series_key: ref.seriesKey,
      chapter_key: ref.chapterKey,
      page,
      note,
    }),

  listBookmarks: (ref?: Partial<SeriesId>) =>
    http.get<Bookmark[]>("/reader/bookmarks", {
      query: { source: ref?.sourceId, series: ref?.seriesKey },
    }),

  deleteBookmark: (bookmarkId: number) =>
    http.delete<void>(`/reader/bookmarks/${bookmarkId}`),
};
