/**
 * OCR is search-only on the web client (spec §3.5). The web queries the global
 * `chapter_ocr` store; it never runs OCR — the mobile client (1c) populates it.
 * There is no queue, no job list, no metrics.
 */

/** One dialogue-search hit, source-native (see backend/services/ocr_search.py). */
export interface OcrSearchResultItem {
  source_id: string;
  series_key: string;
  chapter_key: string;
  word_count: number;
  engine: string;
  /** Server-highlighted excerpt containing literal <mark>…</mark> markers. */
  snippet: string;
  highlighted_terms: string[];
}

export interface OcrSearchResponse {
  items: OcrSearchResultItem[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

/** One page's extracted text (GET /ocr/chapter). */
export interface OcrPageText {
  page: number;
  text: string;
  boxes: unknown[] | null;
}

/**
 * Stored OCR for a single chapter. `page_texts` is empty when the chapter has
 * no transcript yet — the in-reader reveal feature is then silently off.
 */
export interface OcrChapterResponse {
  source_id: string;
  series_key: string;
  chapter_key: string;
  language: string | null;
  engine: string;
  word_count: number;
  updated_at: string | null;
  page_texts: OcrPageText[];
}
