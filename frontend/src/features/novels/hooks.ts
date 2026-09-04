"use client";

import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useReducer } from "react";
import { useBootstrapStatus } from "@/features/auth/hooks";
import { useSources } from "@/features/sources/hooks";
import type { ChapterId, SeriesId } from "@/types/api";
import { novelsApi, toNovelChapter } from "./api";
import { isNovelsEnabled, isNovelSource } from "./gate";
import type { NovelChapterContent, NovelChapterPayload } from "./types";

const NOVELS_KEY = ["novels"] as const;
/** Chapter text is immutable in practice; the server caches it for days. */
const NOVEL_CHAPTER_STALE_MS = 30 * 60_000;

export function novelChapterQueryKey(ref: ChapterId) {
  return [
    ...NOVELS_KEY,
    "chapter",
    ref.sourceId,
    ref.seriesKey,
    ref.chapterKey,
  ] as const;
}

export function useNovelChapter(ref: ChapterId | null) {
  return useQuery({
    queryKey: ref ? novelChapterQueryKey(ref) : [...NOVELS_KEY, "chapter", "none"],
    queryFn: () => novelsApi.chapter(ref!),
    enabled: ref !== null,
    staleTime: NOVEL_CHAPTER_STALE_MS,
  });
}

/** Warm a chapter into the cache and hand back its rendered form. */
export async function ensureNovelChapter(
  queryClient: QueryClient,
  ref: ChapterId,
): Promise<NovelChapterContent> {
  const payload = await queryClient.ensureQueryData({
    queryKey: novelChapterQueryKey(ref),
    queryFn: () => novelsApi.chapter(ref),
    staleTime: NOVEL_CHAPTER_STALE_MS,
  });
  return toNovelChapter(payload);
}

export function prefetchNovelChapter(queryClient: QueryClient, ref: ChapterId) {
  void queryClient.prefetchQuery({
    queryKey: novelChapterQueryKey(ref),
    queryFn: () => novelsApi.chapter(ref),
    staleTime: NOVEL_CHAPTER_STALE_MS,
  });
}

/** Whether this deployment serves novels at all (`/auth/bootstrap-status`). */
export function useNovelsEnabled(): boolean {
  const { data: status } = useBootstrapStatus();
  return isNovelsEnabled(status);
}

/**
 * Whether a given source is a novel source, resolved from the sources listing.
 *
 * `undefined` while the listing is still loading, so a caller can hold a
 * "which reader?" decision for a frame instead of guessing and then swapping
 * the whole screen under the reader.
 */
export function useIsNovelSource(sourceId: string): boolean | undefined {
  const novelsEnabled = useNovelsEnabled();
  const { data: sources } = useSources({ enabled: novelsEnabled });
  if (!novelsEnabled) return false;
  if (!sources) return undefined;
  return isNovelSource(sources.find((source) => source.id === sourceId));
}

/**
 * Word counts for a series' chapters, read out of whatever is already cached.
 *
 * A novel chapter list has no length to show: the connector reports
 * `page_count: 0` (a novel chapter is not made of pages) and there is no bulk
 * word-count endpoint. What there IS is the chapter-text cache — every chapter
 * the reader has opened, plus the handful the series page prefetches and
 * anything hovered — so the list reads its lengths from there and simply says
 * nothing for chapters it has not seen. An honest gap beats a fabricated
 * estimate or a row that claims "0 pages".
 *
 * Subscribes to the query cache once (not one observer per chapter — a novel
 * series can carry two thousand of them) and re-reads on any write under this
 * series' key.
 */
export function useCachedNovelWordCounts(
  ref: SeriesId | null,
): ReadonlyMap<string, number> {
  const queryClient = useQueryClient();
  const [revision, bumpRevision] = useReducer((n: number) => n + 1, 0);
  const sourceId = ref?.sourceId ?? null;
  const seriesKey = ref?.seriesKey ?? null;

  useEffect(() => {
    if (sourceId === null || seriesKey === null) return;
    return queryClient.getQueryCache().subscribe((event) => {
      const key = event.query.queryKey;
      if (
        Array.isArray(key) &&
        key[0] === "novels" &&
        key[1] === "chapter" &&
        key[2] === sourceId &&
        key[3] === seriesKey
      ) {
        bumpRevision();
      }
    });
  }, [queryClient, sourceId, seriesKey]);

  return useMemo(() => {
    const counts = new Map<string, number>();
    if (sourceId === null || seriesKey === null) return counts;
    const entries = queryClient.getQueriesData<NovelChapterPayload>({
      queryKey: [...NOVELS_KEY, "chapter", sourceId, seriesKey],
    });
    for (const [key, payload] of entries) {
      const chapterKey = key[4];
      if (typeof chapterKey !== "string" || !payload) continue;
      const chapter = toNovelChapter(payload);
      if (chapter.wordCount > 0) counts.set(chapterKey, chapter.wordCount);
    }
    return counts;
    // `revision` is the subscription's signal that the cache changed; the
    // cache itself is not reactive, so it has to be in the dependency list —
    // which is exactly the "unnecessary dependency" the rule cannot see.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient, sourceId, seriesKey, revision]);
}
