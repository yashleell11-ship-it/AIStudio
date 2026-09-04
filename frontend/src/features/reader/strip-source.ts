import type { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/types/api";
import { manifestToChapterContent, readerApi } from "./api";
import { READER_CHAPTER_STALE_MS, readerManifestQueryKey } from "./hooks";
import type { StripChapter } from "./strip";

/**
 * Where a strip gets its chapters.
 *
 * Two answers exist and the strip must not care which it has: the plain reader
 * walks the manifest's own `prev`/`next` links (it was opened on one chapter
 * and knows nothing else), while Read-all holds the series' ordered chapter
 * list and pulls windows of it in one request. Both reduce to "name the keys
 * that come next, then fetch them", which is this interface.
 */
export interface StripSource {
  /** Up to `count` keys following the loaded tail. Empty at the end of the series. */
  keysAfter(loaded: readonly StripChapter[], count: number): string[];
  /** The key immediately before the loaded head, or null at the start. */
  keyBefore(loaded: readonly StripChapter[]): string | null;
  /** Fetch those chapters, in the order asked for. */
  fetch(keys: readonly string[]): Promise<StripFetchResult>;
}

export interface StripFetchResult {
  /**
   * The CONTIGUOUS run that resolved, in the order asked for.
   *
   * Contiguous and not merely "the ones that worked": a strip is one scroll, so
   * appending chapter 6 after chapter 4 because 5 failed would silently tell
   * the reader that 4 is followed by 6. A window that fails in the middle
   * therefore contributes its prefix and stops.
   */
  chapters: StripChapter[];
  /** Why the run stopped short, if it did. */
  error: string | null;
}

/** Human-readable reason a chapter did not arrive. */
export function fetchErrorMessage(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  return "That chapter did not load.";
}

/**
 * The plain reader's source: neighbours discovered one at a time from the
 * manifest's own links.
 *
 * It cannot look further than one chapter in either direction, and does not
 * need to — the window it feeds keeps a single chapter either side. Each fetch
 * goes through the reader's ordinary manifest query, so a chapter the series
 * page already prefetched (or one the reader just came back from) costs
 * nothing at all.
 */
export function linkedChapterSource(
  queryClient: QueryClient,
  sourceId: string,
  seriesKey: string,
): StripSource {
  const load = async (chapterKey: string): Promise<StripChapter> => {
    const ref = { sourceId, seriesKey, chapterKey };
    const manifest = await queryClient.ensureQueryData({
      queryKey: readerManifestQueryKey(ref),
      queryFn: () => readerApi.manifest(ref),
      staleTime: READER_CHAPTER_STALE_MS,
    });
    return manifestToChapterContent(manifest);
  };

  return {
    keysAfter(loaded, count) {
      const last = loaded[loaded.length - 1];
      if (!last?.nextChapterKey || count <= 0) return [];
      return [last.nextChapterKey];
    },
    keyBefore(loaded) {
      return loaded[0]?.previousChapterKey ?? null;
    },
    async fetch(keys) {
      const chapters: StripChapter[] = [];
      for (const key of keys) {
        try {
          chapters.push(await load(key));
        } catch (cause) {
          return { chapters, error: fetchErrorMessage(cause) };
        }
      }
      return { chapters, error: null };
    },
  };
}
