import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { libraryApi } from "./api";
import type { SeriesFilter, SeriesSort } from "./types";

const LIBRARY_KEY = ["library"] as const;
const INTELLIGENCE_KEY = ["intelligence"] as const;
/**
 * Membership sits under its own root rather than inside `LIBRARY_KEY` so the
 * broad `invalidateQueries({ queryKey: LIBRARY_KEY })` used by other mutations
 * cannot wipe the optimistic state of every visible toggle. Being a root key
 * also means the `ProfileCacheBoundary` drops it on a profile switch, which is
 * required: the bit is per (user, profile).
 */
const MEMBERSHIP_KEY = ["library-membership"] as const;

// --- Series ---

export function useSeriesList(params: {
  page?: number;
  per_page?: number;
  sort?: SeriesSort;
  search?: string;
  status?: SeriesFilter;
  reading_status?: string;
  collection_id?: number;
  tag_id?: number;
  library_id?: number;
  is_favorite?: boolean;
  language?: string;
}) {
  return useQuery({
    queryKey: [...LIBRARY_KEY, "series", params],
    queryFn: () => libraryApi.listSeries(params),
  });
}

export function useSeries(seriesId: number | null) {
  return useQuery({
    queryKey: [...LIBRARY_KEY, "series", seriesId],
    queryFn: () => libraryApi.getSeries(seriesId!),
    enabled: seriesId !== null,
  });
}

export function useContinueReading(limit = 10) {
  return useQuery({
    queryKey: [...LIBRARY_KEY, "continue-reading", limit],
    queryFn: () => libraryApi.continueReading(limit),
  });
}

// --- Search ---

export function useSearch(params: { q: string; page?: number; per_page?: number }) {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "search", params],
    queryFn: () => libraryApi.search(params),
    enabled: params.q.length > 0,
  });
}

// --- Favorites ---

export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (seriesId: number) => libraryApi.toggleFavorite(seriesId),
    onSuccess: (data) => {
      // Invalidate all series queries that could be affected
      queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
      // Also invalidate the specific series
      queryClient.invalidateQueries({
        queryKey: [...LIBRARY_KEY, "series", data.series_id],
      });
    },
  });
}

// --- Library membership ---

export function libraryMembershipQueryKey(seriesId: number) {
  return [...MEMBERSHIP_KEY, seriesId] as const;
}

/**
 * Whether `seriesId` is on the active profile's shelf, as displayed.
 *
 * There is nothing to fetch: `in_library` rides on the series payload
 * (`_series_summary`, backend/services/library_intelligence_service.py:1570),
 * and callers reached through a membership-gated read (the library grid, local
 * search hits, recommendations, similar) know it is `true` by construction.
 * `seed` is that answer.
 *
 * The query entry is kept because the add/remove mutation writes into it —
 * optimistically on click, then the server's own answer — so every control for
 * the same series flips together and the state survives the refetch the write
 * triggers.
 */
export function useLibraryMembership(seriesId: number, seed: boolean) {
  return useQuery({
    queryKey: libraryMembershipQueryKey(seriesId),
    // No fetcher: the payload already carried the answer, so a refetch could
    // only invent one. `skipToken` disables the query outright.
    queryFn: skipToken,
    initialData: seed,
  });
}

/**
 * Add or remove a series for the active profile, optimistically.
 *
 * The membership bit decides what every gated read returns, so a successful
 * write invalidates the library and discovery caches: a removed series has to
 * disappear from the grid, an added one has to appear in it.
 */
export function useSetLibraryMembership() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ seriesId, inLibrary }: { seriesId: number; inLibrary: boolean }) =>
      inLibrary ? libraryApi.addToLibrary(seriesId) : libraryApi.removeFromLibrary(seriesId),
    onMutate: async ({ seriesId, inLibrary }) => {
      const key = libraryMembershipQueryKey(seriesId);
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<boolean | null>(key);
      queryClient.setQueryData(key, inLibrary);
      return { previous };
    },
    onError: (_error, { seriesId }, context) => {
      const key = libraryMembershipQueryKey(seriesId);
      if (context?.previous === undefined) {
        // Nothing was known before the optimistic write; dropping the entry
        // restores "unknown" (setQueryData ignores an undefined value).
        queryClient.removeQueries({ queryKey: key, exact: true });
        return;
      }
      queryClient.setQueryData(key, context.previous);
    },
    onSuccess: (membership) => {
      queryClient.setQueryData(
        libraryMembershipQueryKey(membership.series_id),
        membership.in_library,
      );
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
      void queryClient.invalidateQueries({ queryKey: INTELLIGENCE_KEY });
    },
  });
}

// --- Recommendations ---

export function useRecommendations(limit = 10) {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "recommendations", limit],
    queryFn: () => libraryApi.recommendations(limit),
  });
}

// --- Similar ---

export function useSimilarSeries(seriesId: number | null, limit = 10) {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "similar", seriesId, limit],
    queryFn: () => libraryApi.similarSeries(seriesId!, limit),
    enabled: seriesId !== null,
  });
}

// --- Reading history ---

export function useReadingHistory(limit = 50) {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "reading-history", limit],
    queryFn: () => libraryApi.readingHistory(limit),
  });
}

export function useReadingCalendar(days = 30) {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "reading-calendar", days],
    queryFn: () => libraryApi.readingCalendar(days),
  });
}

export function useSeriesReadingHistory(seriesId: number | null, limit = 50) {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "series-reading-history", seriesId, limit],
    queryFn: () => libraryApi.seriesReadingHistory(seriesId!, limit),
    enabled: seriesId !== null,
  });
}

// --- Statistics ---

export function useStatistics() {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "statistics"],
    queryFn: () => libraryApi.statistics(),
  });
}

// --- Metadata ---

export function useMetadataQuality(seriesId: number | null) {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "metadata-quality", seriesId],
    queryFn: () => libraryApi.metadataQuality(seriesId!),
    enabled: seriesId !== null,
  });
}

export function useUpdateMetadata() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      seriesId,
      body,
    }: {
      seriesId: number;
      body: Record<string, unknown>;
    }) => libraryApi.updateMetadata(seriesId, body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: [...LIBRARY_KEY, "series", data.id],
      });
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "metadata-quality", data.id],
      });
    },
  });
}

// --- Collections ---

export function useCollections() {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "collections"],
    queryFn: () => libraryApi.listCollections(),
  });
}

export function useCollection(collectionId: number | null) {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "collections", collectionId],
    queryFn: () => libraryApi.getCollection(collectionId!),
    enabled: collectionId !== null,
  });
}

export function useCreateCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) =>
      libraryApi.createCollection(body),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "collections"],
      });
    },
  });
}

export function useUpdateCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      collectionId,
      body,
    }: {
      collectionId: number;
      body: { name?: string; description?: string; sort_order?: number };
    }) => libraryApi.updateCollection(collectionId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "collections"],
      });
    },
  });
}

export function useDeleteCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (collectionId: number) =>
      libraryApi.deleteCollection(collectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "collections"],
      });
    },
  });
}

export function useAddSeriesToCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      collectionId,
      seriesId,
    }: {
      collectionId: number;
      seriesId: number;
    }) => libraryApi.addSeriesToCollection(collectionId, seriesId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "collections", variables.collectionId],
      });
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "collections"],
      });
      queryClient.invalidateQueries({
        queryKey: [...LIBRARY_KEY, "series"],
      });
    },
  });
}

export function useRemoveSeriesFromCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      collectionId,
      seriesId,
    }: {
      collectionId: number;
      seriesId: number;
    }) => libraryApi.removeSeriesFromCollection(collectionId, seriesId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "collections", variables.collectionId],
      });
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "collections"],
      });
      queryClient.invalidateQueries({
        queryKey: [...LIBRARY_KEY, "series"],
      });
    },
  });
}

// --- Tags ---

export function useTags(category?: string) {
  return useQuery({
    queryKey: [...INTELLIGENCE_KEY, "tags", category],
    queryFn: () => libraryApi.listTags(category),
  });
}

export function useCreateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; category?: string; color?: string }) =>
      libraryApi.createTag(body),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "tags"],
      });
    },
  });
}

export function useDeleteTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tagId: number) => libraryApi.deleteTag(tagId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "tags"],
      });
      queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
    },
  });
}

export function useAddTagToSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      seriesId,
      tagId,
    }: {
      seriesId: number;
      tagId: number;
    }) => libraryApi.addTagToSeries(seriesId, tagId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: [...LIBRARY_KEY, "series", variables.seriesId],
      });
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "tags"],
      });
    },
  });
}

export function useRemoveTagFromSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      seriesId,
      tagId,
    }: {
      seriesId: number;
      tagId: number;
    }) => libraryApi.removeTagFromSeries(seriesId, tagId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: [...LIBRARY_KEY, "series", variables.seriesId],
      });
      queryClient.invalidateQueries({
        queryKey: [...INTELLIGENCE_KEY, "tags"],
      });
    },
  });
}

// --- Import ---

export function useScanStatus(enabled: boolean) {
  return useQuery({
    queryKey: [...LIBRARY_KEY, "scan-status"],
    queryFn: () => libraryApi.scanStatus(),
    enabled,
    refetchInterval: enabled ? 1000 : false,
  });
}

export function useImportLibrary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (folderPath: string) => libraryApi.importLibrary(folderPath),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
    },
  });
}
