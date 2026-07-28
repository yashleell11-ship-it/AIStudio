import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { readerDebug } from "@/features/reader/debug";
import { useActiveProfileStore } from "@/features/profiles/store";
import { ApiError } from "@/types/api";
import { sourceImageUrl, sourcesApi } from "./api";
import {
  replaceSearchGroup,
  searchGroupFromSourceSeries,
  searchGroupWithError,
} from "./global-search";
import type {
  GlobalSearchResponse,
  SourceChapterSummary,
  SourcePin,
} from "./types";

const SOURCES_KEY = ["sources"] as const;
const SOURCE_READER_STALE_MS = 5 * 60_000;
const SEARCH_STALE_MS = 30_000;

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

export interface FederatedSearchParams {
  q: string;
  page?: number;
  per_page?: number;
}

export function federatedSearchQueryKey(params: FederatedSearchParams) {
  return [...SOURCES_KEY, "search", params] as const;
}

/**
 * Federated search across the local library and every enabled remote source.
 * Mirrors the local-library `useSearch`: only runs for a non-empty query, keeps
 * previous results while a new query loads (no flicker), and reuses the same
 * short staleTime as the global default so repeated searches stay cached.
 */
export function useFederatedSearch(params: FederatedSearchParams) {
  return useQuery({
    queryKey: federatedSearchQueryKey(params),
    queryFn: () => sourcesApi.federatedSearch(params),
    enabled: params.q.length > 0,
    placeholderData: (previous) => previous,
    staleTime: SEARCH_STALE_MS,
  });
}

/**
 * Re-query one source whose search section failed, patching that section into
 * the cached federated response.
 *
 * Goes to the source's own browse endpoint instead of re-running
 * `/sources/search`: a second federated call pays for every installed source to
 * fix one, and would also replace the sections the user is already reading.
 * `mutation.variables` names the source currently retrying, so only that
 * section shows a spinner.
 */
export function useRetrySearchSource(params: FederatedSearchParams) {
  const queryClient = useQueryClient();
  const key = federatedSearchQueryKey(params);

  const patch = (
    sourceId: string,
    rebuild: (
      previous: GlobalSearchResponse,
      group: GlobalSearchResponse["groups"][number],
    ) => GlobalSearchResponse,
  ) => {
    queryClient.setQueryData<GlobalSearchResponse>(key, (previous) => {
      if (!previous) return previous;
      const group = previous.groups.find((entry) => entry.source === sourceId);
      // A newer query already replaced these results; the retry answer is stale.
      if (!group) return previous;
      return rebuild(previous, group);
    });
  };

  return useMutation({
    mutationFn: (sourceId: string) =>
      sourcesApi.listSeries(sourceId, { query: params.q }),
    onSuccess: (page, sourceId) => {
      patch(sourceId, (previous, group) =>
        replaceSearchGroup(
          previous,
          searchGroupFromSourceSeries(group, page, sourceImageUrl),
        ),
      );
    },
    onError: (error, sourceId) => {
      const message =
        error instanceof ApiError ? error.message : "This source did not answer.";
      patch(sourceId, (previous, group) =>
        replaceSearchGroup(previous, searchGroupWithError(group, message)),
      );
    },
  });
}

export function sourcePinsQueryKey(profileId: number | null) {
  return [...SOURCES_KEY, "pins", profileId] as const;
}

/**
 * The active profile's pinned sources.
 *
 * The profile id is part of the cache key on purpose: pins are stored per
 * `(user_id, profile_id)`, so a switch must never render the previous profile's
 * shortcuts out of cache. The `ProfileCacheBoundary` already drops
 * profile-scoped queries on a switch; keying makes a stale hit structurally
 * impossible rather than dependent on that boundary firing.
 *
 * Disabled without an active profile: the write path requires `X-Profile-Id`,
 * and a profile-less read answers for the account's unscoped bucket, which is a
 * different set that must not be shown as "your pins".
 */
export function useSourcePins() {
  const profileId = useActiveProfileStore((state) => state.activeProfile?.id ?? null);
  return useQuery({
    queryKey: sourcePinsQueryKey(profileId),
    queryFn: () => sourcesApi.listPins(),
    enabled: profileId !== null,
  });
}

/**
 * Replace the pinned set, optimistically. Callers pass the complete next list
 * (see `pins.ts`), which is also the shape the endpoint takes.
 */
export function useReplaceSourcePins() {
  const queryClient = useQueryClient();
  const profileId = useActiveProfileStore((state) => state.activeProfile?.id ?? null);
  const key = sourcePinsQueryKey(profileId);
  return useMutation({
    mutationFn: (next: SourcePin[]) =>
      sourcesApi.replacePins(next.map((pin) => pin.source_id)),
    onMutate: async (next) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<SourcePin[]>(key);
      queryClient.setQueryData<SourcePin[]>(key, next);
      return { previous };
    },
    onError: (_error, _next, context) => {
      queryClient.setQueryData<SourcePin[] | undefined>(key, context?.previous);
    },
    onSuccess: (server) => {
      // The server resolves each pin's display name, icon and 18+ flag, so its
      // answer supersedes the optimistic rows rather than merely confirming them.
      queryClient.setQueryData<SourcePin[]>(key, server);
    },
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
