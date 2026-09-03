import { useQuery } from "@tanstack/react-query";
import type { ChapterId } from "@/types/api";
import { ApiError } from "@/types/api";
import { ocrApi } from "./api";

const OCR_KEY = ["ocr"] as const;

/**
 * Dialogue search over extracted OCR text. Disabled (no request) until a
 * non-empty query is supplied; callers should debounce the raw input before
 * passing it here so keystrokes don't each fire a request.
 */
export function useOcrSearch(query: string) {
  const q = query.trim();
  return useQuery({
    queryKey: [...OCR_KEY, "search", q],
    queryFn: () => ocrApi.search({ q, limit: 20 }),
    enabled: q.length > 0,
  });
}

/**
 * Stored per-page OCR text for one chapter, for the in-reader dialogue reveal.
 * Read-only: a 404 (no transcript yet) resolves to `null` rather than erroring,
 * so the feature is simply off for that chapter.
 */
export function useOcrChapter(ref: ChapterId | null) {
  return useQuery({
    queryKey: [
      ...OCR_KEY,
      "chapter",
      ref?.sourceId ?? "",
      ref?.seriesKey ?? "",
      ref?.chapterKey ?? "",
    ],
    queryFn: async () => {
      try {
        return await ocrApi.chapter(ref!);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled: ref !== null,
    staleTime: 5 * 60_000,
  });
}
