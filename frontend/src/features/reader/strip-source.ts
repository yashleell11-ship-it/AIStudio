import type { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/types/api";
import { manifestToChapterContent, readerApi, type ChapterManifest } from "./api";
import {
  keyBefore,
  orderedLabel,
  windowAfter,
  windowBefore,
  windowFrom,
  type OrderedChapter,
} from "./read-all";
import { READER_CHAPTER_STALE_MS, readerManifestQueryKey } from "./hooks";
import { nextChapterLabelFor, type StripChapter } from "./strip";

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
  /**
   * The window the strip OPENS with: up to `count` keys starting at the entry
   * chapter itself.
   *
   * Separate from `keysAfter` because the strip has nothing loaded yet and
   * cannot ask "what follows this". A source that can name the chapters after
   * the entry one answers with them, so opening a run costs a single round trip
   * instead of one for the entry chapter and a second, strictly after it, for
   * the window behind it.
   */
  entryKeys(entryChapterKey: string, count: number): string[];
  /** Up to `count` keys following the loaded tail. Empty at the end of the series. */
  keysAfter(loaded: readonly StripChapter[], count: number): string[];
  /** The key immediately before the loaded head, or null at the start. */
  keyBefore(loaded: readonly StripChapter[]): string | null;
  /**
   * Up to `count` keys before the loaded head, in reading order.
   *
   * `keyBefore` names the one chapter the head could grow into; this names the
   * window worth asking for in one request. A source whose transport carries
   * many chapters per call widens `count` on its own, exactly as `keysAfter`
   * does — scrolling backwards must not cost a round trip per chapter when
   * going forwards costs one per six.
   */
  keysBefore(loaded: readonly StripChapter[], count: number): string[];
  /**
   * What to call the chapter just outside one end of the strip.
   *
   * The source knows more than the strip does: Read-all holds the series'
   * chapter list and can name the real number, while the plain reader has only
   * the neighbour's key and has to infer it from the chapter it is beside.
   */
  edgeLabel(loaded: readonly StripChapter[], direction: "next" | "previous"): string | null;
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
  /**
   * How long to wait before the strip should try again on its own.
   *
   * Only set for a failure that time alone fixes — the bulk window's rate limit
   * (one call is worth up to twenty upstream scrapes, so the server allows six
   * a minute). A Read-all session that hits it must resume by itself; a reader
   * fifty chapters deep should not have to press anything.
   */
  retryAfterMs?: number;
}

/** How long to wait out a rate-limited window before trying it again. */
const RATE_LIMIT_RETRY_MS = 12_000;

/** Human-readable reason a chapter did not arrive. */
function fetchErrorMessage(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 429) {
      return "Asking the source for chapters faster than it allows — picking up again shortly.";
    }
    return cause.message;
  }
  return "That chapter did not load.";
}

/** A failure that will pass on its own, and how long that takes. */
function retryDelayFor(cause: unknown): number | undefined {
  return cause instanceof ApiError && cause.status === 429
    ? RATE_LIMIT_RETRY_MS
    : undefined;
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
    entryKeys(entryChapterKey) {
      // A chapter's own links are all this source has, and they are inside the
      // manifest it has not fetched yet. The window can only be the one key.
      return [entryChapterKey];
    },
    keysAfter(loaded, count) {
      const last = loaded[loaded.length - 1];
      if (!last?.nextChapterKey || count <= 0) return [];
      return [last.nextChapterKey];
    },
    keyBefore(loaded) {
      return loaded[0]?.previousChapterKey ?? null;
    },
    keysBefore(loaded, count) {
      const key = loaded[0]?.previousChapterKey;
      return key && count > 0 ? [key] : [];
    },
    edgeLabel(loaded, direction) {
      const edge = direction === "next" ? loaded[loaded.length - 1] : loaded[0];
      return edge ? nextChapterLabelFor(edge, direction) : null;
    },
    async fetch(keys) {
      const chapters: StripChapter[] = [];
      for (const key of keys) {
        try {
          chapters.push(await load(key));
        } catch (cause) {
          return {
            chapters,
            error: fetchErrorMessage(cause),
            retryAfterMs: retryDelayFor(cause),
          };
        }
      }
      return { chapters, error: null };
    },
  };
}

/**
 * Chapters per bulk window the client will ask for.
 *
 * The server's own cap arrives on every answer as `max_chapters` and wins over
 * this the moment one lands; until then the endpoint's documented default is
 * the safe assumption. A stride rather than a chapter at a time because the
 * bulk bucket is rate-limited per CALL: one window of six spends the same
 * budget as one chapter, and a run through a long series must not stall on it.
 */
const BULK_WINDOW_STRIDE = 6;
const BULK_WINDOW_CAP = 20;

/**
 * Chapters per window when the strip grows BACKWARDS.
 *
 * Deliberately shorter than the forward stride. Going forwards a Read-all
 * reader has declared they are reading the rest of the series, so the chance
 * every chapter in the window gets shown is close to one and a full stride is
 * honest. Backwards is a single overscroll gesture: half a stride is enough
 * that re-reading the last couple of chapters does not cost a round trip each,
 * without spending six upstream scrapes on a maybe.
 */
const BULK_BACKWARD_STRIDE = 3;

/**
 * Read-all's source: an ordered series list plus the bulk manifest endpoint.
 *
 * Two things it does that the linked source cannot. It knows the real reading
 * order, so a connector that lists newest-first cannot send the run backwards;
 * and it pulls a window of chapters in ONE request, which is what makes opening
 * a three-hundred-chapter series stream instead of spin.
 *
 * Manifests land in the reader's ordinary per-chapter cache on the way past, so
 * a window the reader has already crossed costs nothing to re-enter, and
 * opening one of its chapters in the plain reader is instant.
 */
export function bulkChapterSource(
  queryClient: QueryClient,
  sourceId: string,
  seriesKey: string,
  order: readonly OrderedChapter[],
  cap: number = BULK_WINDOW_CAP,
): StripSource {
  const cached = (chapterKey: string): StripChapter | undefined => {
    const manifest = queryClient.getQueryData<ChapterManifest>(
      readerManifestQueryKey({ sourceId, seriesKey, chapterKey }),
    );
    return manifest ? manifestToChapterContent(manifest) : undefined;
  };

  /**
   * The cap actually in force. `cap` is only the assumption held until the
   * server states its own, which `MM_READER_BULK_MAX_CHAPTERS` can retune at
   * any time: a window over that cap comes back 413 for the WHOLE window, which
   * stops a run dead with no retry, so the answer's `max_chapters` replaces it.
   */
  let windowCap = Math.max(1, Math.floor(cap));

  return {
    entryKeys(entryChapterKey, count) {
      const window = windowFrom(order, entryChapterKey, count, windowCap);
      // An entry chapter outside the series list can still be read on its own;
      // opening on nothing at all would be the worse answer.
      return window.length > 0 ? window : [entryChapterKey];
    },
    keysAfter(loaded, count) {
      return windowAfter(
        order,
        loaded[loaded.length - 1]?.chapterKey,
        count,
        BULK_WINDOW_STRIDE,
        windowCap,
      );
    },
    keyBefore(loaded) {
      return keyBefore(order, loaded[0]?.chapterKey);
    },
    keysBefore(loaded, count) {
      return windowBefore(
        order,
        loaded[0]?.chapterKey,
        Math.max(count, BULK_BACKWARD_STRIDE),
        windowCap,
      );
    },
    edgeLabel(loaded, direction) {
      const key =
        direction === "next"
          ? windowAfter(order, loaded[loaded.length - 1]?.chapterKey, 1, 1, windowCap)[0] ??
            null
          : keyBefore(order, loaded[0]?.chapterKey);
      return orderedLabel(order, key);
    },
    async fetch(keys) {
      // Only ask for what is not already in hand: re-entering a window the
      // reader has crossed before must not cost the source a single request.
      const missing = keys.filter((key) => cached(key) === undefined);
      const failures = new Map<string, string>();

      if (missing.length > 0) {
        try {
          const response = await readerApi.manifestBatch(
            { sourceId, seriesKey },
            missing,
          );
          // The server's cap wins from the first answer that carries one.
          if (Number.isFinite(response.max_chapters) && response.max_chapters > 0) {
            windowCap = Math.max(1, Math.floor(response.max_chapters));
          }
          for (const item of response.items) {
            if (item.status === "ok" && item.manifest) {
              queryClient.setQueryData(
                readerManifestQueryKey({
                  sourceId,
                  seriesKey,
                  chapterKey: item.chapter_key,
                }),
                item.manifest,
              );
            } else if (item.error) {
              failures.set(item.chapter_key, item.error.message);
            }
          }
        } catch (cause) {
          // A whole-window failure: the gate, the series, the cap, or the rate
          // limit. Nothing in this window is usable.
          return {
            chapters: [],
            error: fetchErrorMessage(cause),
            retryAfterMs: retryDelayFor(cause),
          };
        }
      }

      const chapters: StripChapter[] = [];
      for (const key of keys) {
        const chapter = cached(key);
        if (!chapter) {
          return {
            chapters,
            error: failures.get(key) ?? "That chapter did not load.",
          };
        }
        chapters.push(chapter);
      }
      return { chapters, error: null };
    },
  };
}
