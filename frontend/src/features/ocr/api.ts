import { http, sourceChapterQuery } from "@/services/http";
import type { ChapterId } from "@/types/api";
import type { OcrChapterResponse, OcrSearchResponse } from "./types";

/**
 * OCR is search-only here (spec §3.5): dialogue search over the global
 * `chapter_ocr` store, plus a read of one chapter's stored `page_texts`. No
 * queue / jobs / metrics — the web client never runs OCR.
 */
export const ocrApi = {
  search: (params: { q: string; limit?: number; offset?: number }) =>
    http.get<OcrSearchResponse>("/ocr/search", { query: params }),

  /** Stored transcript for one chapter, or 404 when none exists yet. */
  chapter: (ref: ChapterId) =>
    http.get<OcrChapterResponse>("/ocr/chapter", {
      query: sourceChapterQuery(ref),
    }),
};
