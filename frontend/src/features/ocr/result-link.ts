import { readerChapterHref } from "@/features/reader/reader-link";
import type { OcrSearchResultItem } from "./types";

/**
 * The reader URL for an OCR search hit.
 *
 * `GET /ocr/search` returns no page offset (the FTS index is per chapter, not
 * per page), so the link opens the chapter at its start. The reader then
 * restores the reader's own saved progress if any.
 */
export function ocrResultHref(item: OcrSearchResultItem): string {
  return readerChapterHref({
    sourceId: item.source_id,
    seriesKey: item.series_key,
    chapterKey: item.chapter_key,
  });
}
