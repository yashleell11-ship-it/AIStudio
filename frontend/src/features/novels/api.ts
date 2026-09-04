import { http, sourceChapterQuery } from "@/services/http";
import type { ChapterId } from "@/types/api";
import { bucketCount } from "./progress";
import { countWords } from "./reading-time";
import type { NovelChapterContent, NovelChapterPayload } from "./types";

/**
 * Build a renderable chapter from the wire payload. The sole content builder,
 * mirroring the manga reader's `manifestToChapterContent`.
 *
 * The title falls back to the chapter number and then to a bare "Chapter":
 * novel aggregators routinely publish untitled chapters, and a blank heading
 * in the middle of a continuous scroll is worse than a generic one.
 *
 * `word_count` is trusted when the server sent one and recomputed from the
 * paragraphs when it did not (an older cache row, a payload shape that
 * changed) — the reading-time estimate is the main thing a reader looks at
 * before opening a chapter, so "unknown" is worth a cheap local count.
 */
export function toNovelChapter(payload: NovelChapterPayload): NovelChapterContent {
  const paragraphs = Array.isArray(payload.paragraphs) ? payload.paragraphs : [];
  const title =
    payload.title?.trim() ||
    (payload.chapter_number != null ? `Chapter ${payload.chapter_number}` : "Chapter");
  return {
    sourceId: payload.source_id,
    seriesKey: payload.series_key,
    chapterKey: payload.chapter_key,
    chapterNumber: payload.chapter_number,
    title,
    paragraphs,
    previousChapterKey: payload.prev,
    nextChapterKey: payload.next,
    wordCount: payload.word_count > 0 ? payload.word_count : countWords(paragraphs),
    buckets: bucketCount(paragraphs.length),
    cache: payload.cache ?? null,
  };
}

export const novelsApi = {
  /**
   * One chapter as sanitized plain-text paragraphs.
   *
   * Query-param identity, like every other source-native endpoint: connector
   * keys are opaque and routinely contain `/`, so they are never path segments
   * here. 404s when `MM_NOVELS_ENABLED` is off — the whole router is unmounted,
   * so an off feature is indistinguishable from one that was never built.
   */
  chapter: (ref: ChapterId) =>
    http.get<NovelChapterPayload>("/novels/chapter", {
      query: sourceChapterQuery(ref),
    }),
};
