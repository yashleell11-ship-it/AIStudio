import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { libraryApi } from "./api";
import type { SeriesFilter, SeriesSort } from "./types";

const LIBRARY_KEY = ["library"] as const;
const INTELLIGENCE_KEY = ["intelligence"] as const;

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
