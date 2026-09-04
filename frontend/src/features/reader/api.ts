import { env } from "@/config/env";
import { http, sourceChapterQuery } from "@/services/http";
import type { ChapterId, SeriesId } from "@/types/api";
import type { ReaderChapterContent, ReaderPage } from "./types";

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

/** One chapter's slot in a bulk-manifest window (`POST /reader/chapters/manifest`). */
export interface BulkManifestItem {
  chapter_key: string;
  status: "ok" | "error";
  /** Byte-identical to what `GET /reader/chapter/manifest` serves, or null. */
  manifest: ChapterManifest | null;
  /** Exactly one of `manifest` / `error` is non-null. */
  error: { code: string; status: number; message: string } | null;
}

/**
 * `POST /reader/chapters/manifest` — manifests for a WINDOW of chapters in one
 * round trip (backend `ReaderService.manifest_batch`).
 *
 * `items` is the same length and order as the keys asked for, and degrades per
 * chapter: an upstream failure on one of them is an `error` item, not a failed
 * window. `max_chapters` is the server's cap, echoed on every answer so the
 * client pages by the server's stride instead of hard-coding one.
 */
export interface BulkManifestResponse {
  source_id: string;
  series_key: string;
  max_chapters: number;
  requested: number;
  ok_count: number;
  failed_count: number;
  items: BulkManifestItem[];
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

  /**
   * A window of chapters' manifests. POST, not GET: the body is a list of
   * opaque keys that routinely contain slashes, and twenty of them do not
   * belong in a query string. It is still a read — nothing here mutates.
   */
  manifestBatch: (ref: SeriesId, chapterKeys: readonly string[]) =>
    http.post<BulkManifestResponse>("/reader/chapters/manifest", {
      source_id: ref.sourceId,
      series_key: ref.seriesKey,
      chapter_keys: chapterKeys,
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
};
