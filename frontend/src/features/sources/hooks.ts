import { useInfiniteQuery, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { readerDebug } from "@/features/reader/debug";
import { sourcesApi } from "./api";
import type { SourceChapterSummary } from "./types";

const SOURCES_KEY = ["sources"] as const;
const SOURCE_READER_STALE_MS = 5 * 60_000;

export function sourceReaderChapterQueryKey(
  sourceId: string,
  seriesId: string,
  chapterId: string,
) {
  return [...SOURCES_KEY, sourceId, "reader", seriesId, chapterId] as const;
}

export function prefetchSourceReaderChapter(
  queryClient: ReturnType<typeof useQueryClient>,
  sourceId: string,
  seriesId: string,
  chapterId: string,
) {
  if (!sourceId || !seriesId || !chapterId) return;
  readerDebug("api-prefetch-started", {
    sourceId,
    seriesId,
    chapterId,
    scope: "source",
  });
  void queryClient
    .prefetchQuery({
      queryKey: sourceReaderChapterQueryKey(sourceId, seriesId, chapterId),
      queryFn: () => sourcesApi.getReaderChapter(sourceId, seriesId, chapterId),
      staleTime: SOURCE_READER_STALE_MS,
    })
    .then(() => {
      readerDebug("api-prefetch-complete", {
        sourceId,
        seriesId,
        chapterId,
        scope: "source",
      });
    });
}

export function sourceReaderChapterPath(
  sourceId: string,
  seriesId: string,
  chapterId: string,
): string {
  return `/reader/online/${encodeURIComponent(sourceId)}/${encodeURIComponent(seriesId)}/${encodeURIComponent(chapterId)}`;
}

export function useSources() {
  return useQuery({
    queryKey: [...SOURCES_KEY, "installed"],
    queryFn: () => sourcesApi.listSources(),
  });
}

export function useSourceBrowseModes(sourceId: string) {
  return useQuery({
    queryKey: [...SOURCES_KEY, sourceId, "browse-modes"],
    queryFn: () => sourcesApi.browseModes(sourceId),
    enabled: Boolean(sourceId),
  });
}

export function useSourceGenres(sourceId: string) {
  return useQuery({
    queryKey: [...SOURCES_KEY, sourceId, "genres"],
    queryFn: () => sourcesApi.genres(sourceId),
    enabled: Boolean(sourceId),
  });
}

export function useSourceSeries(
  sourceId: string,
  params: { page?: number; query?: string; sort?: string; genre?: string },
) {
  return useQuery({
    queryKey: [...SOURCES_KEY, sourceId, "series", params],
    queryFn: () => sourcesApi.listSeries(sourceId, params),
    enabled: Boolean(sourceId),
    placeholderData: (previous) => previous,
  });
}

export function useInfiniteSourceSeries(
  sourceId: string,
  query: string,
  sort?: string,
  genre?: string,
) {
  const normalizedQuery = query.trim();
  const normalizedSort = sort && sort !== "default" ? sort : undefined;
  const normalizedGenre = genre?.trim() || undefined;
  return useInfiniteQuery({
    queryKey: [
      ...SOURCES_KEY,
      sourceId,
      "series",
      "infinite",
      normalizedQuery,
      normalizedSort ?? "",
      normalizedGenre ?? "",
    ],
    queryFn: ({ pageParam }) =>
      sourcesApi.listSeries(sourceId, {
        page: pageParam,
        query: normalizedQuery || undefined,
        sort: normalizedSort,
        genre: normalizedGenre,
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.page + 1 : undefined),
    enabled: Boolean(sourceId),
  });
}

export function useSourceSeriesDetail(sourceId: string, seriesId: string) {
  return useQuery({
    queryKey: [...SOURCES_KEY, sourceId, "series", seriesId],
    queryFn: () => sourcesApi.getSeries(sourceId, seriesId),
    enabled: Boolean(sourceId) && Boolean(seriesId),
  });
}

export function sourceChaptersQueryKey(sourceId: string, seriesId: string) {
  return [...SOURCES_KEY, sourceId, "series", seriesId, "chapters"] as const;
}

export function useSourceChapters(sourceId: string, seriesId: string) {
  return useQuery({
    queryKey: sourceChaptersQueryKey(sourceId, seriesId),
    queryFn: () => sourcesApi.getChapters(sourceId, seriesId),
    enabled: Boolean(sourceId) && Boolean(seriesId),
    // Chapter lists must reflect upstream changes quickly; a stale empty
    // response (e.g. after a transient scrape miss) otherwise sticks for 30s.
    staleTime: 0,
  });
}

/**
 * Connectors only learn a chapter's page_count after its pages have been
 * fetched at least once (the series-chapters HTML has no per-chapter counts
 * up front). The chapters list query has no way to know that fetching a
 * reader chapter just changed its own data server-side, so it kept serving
 * its cached (page_count: 0) response until it happened to go stale on its
 * own, up to 30s (the global default staleTime) later.
 *
 * Call this once the reader chapter succeeds. It patches the cached chapter
 * entry in place via `setQueryData` -- an instant, local update with no
 * extra network request -- so the series page reflects the real count the
 * moment the reader chapter finishes loading. Only when there is no usable
 * cached list to patch (not yet fetched, or the chapter isn't in it) does it
 * fall back to invalidating that one series' chapters query, and only that
 * one: no other cached query is touched.
 */
export function applyReaderPageCountToSourceChapters(
  queryClient: QueryClient,
  sourceId: string,
  seriesId: string,
  chapterId: string,
  pageCount: number,
): void {
  const key = sourceChaptersQueryKey(sourceId, seriesId);
  let patched = false;

  queryClient.setQueryData<SourceChapterSummary[]>(key, (previous) => {
    if (!previous) return previous;
    let changed = false;
    const next = previous.map((chapter) => {
      if (chapter.id === chapterId && chapter.page_count !== pageCount) {
        changed = true;
        return { ...chapter, page_count: pageCount };
      }
      return chapter;
    });
    if (!changed) return previous;
    patched = true;
    return next;
  });

  if (!patched) {
    void queryClient.invalidateQueries({ queryKey: key });
  }
}

export function useSourceReaderChapter(
  sourceId: string,
  seriesId: string,
  chapterId: string,
) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: sourceReaderChapterQueryKey(sourceId, seriesId, chapterId),
    queryFn: async () => {
      readerDebug("api-request-started", {
        sourceId,
        seriesId,
        chapterId,
        scope: "source",
      });
      const payload = await sourcesApi.getReaderChapter(sourceId, seriesId, chapterId);
      readerDebug("api-response-received", {
        sourceId,
        seriesId,
        chapterId,
        scope: "source",
        pageCount: payload.page_count,
      });
      applyReaderPageCountToSourceChapters(
        queryClient,
        sourceId,
        seriesId,
        chapterId,
        payload.page_count,
      );
      return payload;
    },
    enabled: Boolean(sourceId) && Boolean(seriesId) && Boolean(chapterId),
    staleTime: SOURCE_READER_STALE_MS,
  });
}
