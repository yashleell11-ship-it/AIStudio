import type { ChapterId, SeriesId } from "@/types/api";
import type { SourceBrowseCache } from "@/features/sources/types";

export type { ChapterId, SeriesId };

/**
 * `GET /novels/chapter?source=&series=&chapter=` — the novel analog of the
 * reader manifest (`backend/services/novel_service.py`).
 *
 * `paragraphs` is SANITIZED PLAIN TEXT, never HTML: the connector strips
 * scripts, styles, ads and aggregator watermark lines before anything is
 * cached, so what arrives here is the canonical storage form (and, later, the
 * TTS input). Rendering it as text rather than `dangerouslySetInnerHTML` is
 * therefore both the safe choice and the accurate one.
 *
 * `cache` is the same block the browse endpoints carry — `stale` means the
 * source could not be reached and this is the last good copy.
 */
export interface NovelChapterPayload {
  source_id: string;
  series_key: string;
  chapter_key: string;
  title: string | null;
  chapter_number: number | null;
  paragraphs: string[];
  /** Adjacent chapter keys, or null at the ends of the series. */
  prev: string | null;
  next: string | null;
  word_count: number;
  cache?: SourceBrowseCache | null;
}

/** A chapter ready to render, built from the payload by `toNovelChapter`. */
export interface NovelChapterContent {
  sourceId: string;
  seriesKey: string;
  chapterKey: string;
  chapterNumber: number | null;
  title: string;
  paragraphs: string[];
  previousChapterKey: string | null;
  nextChapterKey: string | null;
  wordCount: number;
  /** How many progress buckets this chapter's paragraphs map onto. */
  buckets: number;
  cache: SourceBrowseCache | null;
}
