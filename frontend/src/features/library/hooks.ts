// Holds React state (`useState`/`useRef`) via `useBulkSeriesAction`, so the
// whole module is client-only. The `@/features/library` barrel re-exports it
// into Server Components, which Turbopack refuses without this directive.
"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import type { SeriesId } from "@/types/api";
import { libraryApi } from "./api";
import {
  type BulkOutcome,
  type BulkProgress,
  runBulk,
  summarizeBulkOutcome,
} from "./bulk";
import {
  clientTimezoneOffsetMinutes,
  DEFAULT_STATISTICS_RANGE,
} from "./reading-stats";
import type { SeriesListParams } from "./url-state";
import type { FollowedSeries } from "./types";

/**
 * Cache roots for the two library namespaces. Exported because the backend
 * filters everything under both by the profile's 18+ gate, so flipping that
 * gate has to invalidate them — see `preferences/mature-gate.ts`.
 */
export const LIBRARY_QUERY_ROOT = "library" as const;
export const LIBRARY_DISCOVERY_QUERY_ROOT = "library-discovery" as const;

const LIBRARY_KEY = [LIBRARY_QUERY_ROOT] as const;
const DISCOVERY_KEY = [LIBRARY_DISCOVERY_QUERY_ROOT] as const;

// --- Followed series ---

export function useSeriesList(params: SeriesListParams) {
  return useQuery({
    queryKey: [...LIBRARY_KEY, "series", params],
    queryFn: () => libraryApi.listSeries(params),
  });
}

export function seriesQueryKey(followedId: number | null) {
  return [...LIBRARY_KEY, "series-detail", followedId] as const;
}

export function useSeries(followedId: number | null) {
  return useQuery({
    queryKey: seriesQueryKey(followedId),
    queryFn: () => libraryApi.getSeries(followedId!),
    enabled: followedId !== null,
  });
}

export function useContinueReading(limit = 10) {
  return useQuery({
    queryKey: [...LIBRARY_KEY, "continue-reading", limit],
    queryFn: () => libraryApi.continueReading(limit),
  });
}

// --- Search over the followed set ---

export function useSearch(params: { q: string; page?: number; per_page?: number }) {
  return useQuery({
    queryKey: [...DISCOVERY_KEY, "search", params],
    queryFn: () => libraryApi.search(params),
    enabled: params.q.length > 0,
  });
}

// --- Follow / unfollow ---

/**
 * Map of `"sourceId:seriesKey" -> followed_id` over the whole followed set, so
 * a `FollowButton` anywhere can tell whether its series is followed and get the
 * id it needs to unfollow. One request, shared cache.
 */
export function useFollowedIndex() {
  const query = useQuery({
    queryKey: [...LIBRARY_KEY, "followed-index"],
    queryFn: () => libraryApi.listSeries({ per_page: 200, sort: "title" }),
  });
  const index = new Map<string, number>();
  const titles = new Map<string, string>();
  for (const row of query.data?.items ?? []) {
    const key = `${row.source_id}:${row.series_key}`;
    index.set(key, row.id);
    if (row.title) titles.set(key, row.title);
  }
  return { ...query, index, titles };
}

export function followKey(ref: SeriesId): string {
  return `${ref.sourceId}:${ref.seriesKey}`;
}

export function useFollow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ref: SeriesId) => libraryApi.follow(ref),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
    },
  });
}

export function useUnfollow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (followedId: number) => libraryApi.unfollow(followedId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
    },
  });
}

// --- Follow-row patches ---

export interface SeriesPatch {
  is_favorite?: boolean;
  reading_status?: string;
  notify?: boolean;
  mature_override?: boolean;
  sort_order?: number;
}

export function usePatchSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ followedId, body }: { followedId: number; body: SeriesPatch }) =>
      libraryApi.patchSeries(followedId, body),
    onSuccess: (data: FollowedSeries) => {
      void queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
      queryClient.setQueryData(seriesQueryKey(data.id), (prev: unknown) =>
        prev && typeof prev === "object" ? { ...prev, ...data } : prev,
      );
    },
  });
}

export function useToggleFavorite() {
  const patch = usePatchSeries();
  return {
    ...patch,
    mutate: ({ followedId, isFavorite }: { followedId: number; isFavorite: boolean }) =>
      patch.mutate({ followedId, body: { is_favorite: isFavorite } }),
  };
}

// --- Discovery ---

export function useRecommendations(limit = 10) {
  return useQuery({
    queryKey: [...DISCOVERY_KEY, "recommendations", limit],
    queryFn: () => libraryApi.recommendations(limit),
  });
}

export function useReadingHistory(limit = 50) {
  return useQuery({
    queryKey: [...DISCOVERY_KEY, "reading-history", limit],
    queryFn: () => libraryApi.readingHistory(limit),
  });
}

/**
 * Reading statistics for one window.
 *
 * The viewer's UTC offset is part of the request (the backend buckets days at
 * it) and therefore part of the cache key — a profile that crosses a timezone
 * must not be served yesterday's buckets. It is read once per render rather
 * than stored, so a laptop opened in another country is right on the next
 * fetch without anything to invalidate.
 */
export function useStatistics(days: number = DEFAULT_STATISTICS_RANGE) {
  const tzOffsetMinutes = clientTimezoneOffsetMinutes();
  return useQuery({
    queryKey: [...DISCOVERY_KEY, "statistics", days, tzOffsetMinutes],
    queryFn: () =>
      libraryApi.statistics({ days, tz_offset_minutes: tzOffsetMinutes }),
  });
}

// --- Bookmarks ---

export function useBookmarks(ref?: Partial<SeriesId>) {
  return useQuery({
    queryKey: [...DISCOVERY_KEY, "bookmarks", ref?.sourceId, ref?.seriesKey],
    queryFn: () => libraryApi.listBookmarks(ref),
  });
}

export function useDeleteBookmark() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bookmarkId: number) => libraryApi.deleteBookmark(bookmarkId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...DISCOVERY_KEY, "bookmarks"],
      });
    },
  });
}

// --- Collections ---

export function useCollections() {
  return useQuery({
    queryKey: [...DISCOVERY_KEY, "collections"],
    queryFn: () => libraryApi.listCollections(),
  });
}

export function useCollection(collectionId: number | null) {
  return useQuery({
    queryKey: [...DISCOVERY_KEY, "collections", collectionId],
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
      void queryClient.invalidateQueries({
        queryKey: [...DISCOVERY_KEY, "collections"],
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
      void queryClient.invalidateQueries({
        queryKey: [...DISCOVERY_KEY, "collections"],
      });
    },
  });
}

export function useDeleteCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (collectionId: number) => libraryApi.deleteCollection(collectionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...DISCOVERY_KEY, "collections"],
      });
    },
  });
}

export function useAddSeriesToCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionId, ref }: { collectionId: number; ref: SeriesId }) =>
      libraryApi.addSeriesToCollection(collectionId, ref),
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({
        queryKey: [...DISCOVERY_KEY, "collections", variables.collectionId],
      });
      void queryClient.invalidateQueries({
        queryKey: [...DISCOVERY_KEY, "collections"],
      });
    },
  });
}

export function useRemoveSeriesFromCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionId, ref }: { collectionId: number; ref: SeriesId }) =>
      libraryApi.removeSeriesFromCollection(collectionId, ref),
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({
        queryKey: [...DISCOVERY_KEY, "collections", variables.collectionId],
      });
      void queryClient.invalidateQueries({
        queryKey: [...DISCOVERY_KEY, "collections"],
      });
    },
  });
}

// --- Tags ---

export function useTags(category?: string) {
  return useQuery({
    queryKey: [...DISCOVERY_KEY, "tags", category],
    queryFn: () => libraryApi.listTags(category),
  });
}

export function useCreateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; category?: string; color?: string }) =>
      libraryApi.createTag(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...DISCOVERY_KEY, "tags"] });
    },
  });
}

export function useDeleteTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tagId: number) => libraryApi.deleteTag(tagId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...DISCOVERY_KEY, "tags"] });
    },
  });
}

export function useAddTagToSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ref, tagId }: { ref: SeriesId; tagId: number }) =>
      libraryApi.addTagToSeries(ref, tagId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
    },
  });
}

export function useRemoveTagFromSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ref, tagId }: { ref: SeriesId; tagId: number }) =>
      libraryApi.removeTagFromSeries(ref, tagId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
    },
  });
}

// --- Bulk actions over the followed grid ---

/**
 * What a bulk action does to one followed series. Membership means unfollow —
 * bulk re-follow is not offered (it needs the `(source, series_key)` pair per
 * row, which the grid has, but the undo path is a later slice).
 */
export type BulkAction =
  | { kind: "favorite"; value: boolean }
  | { kind: "reading_status"; value: string }
  | { kind: "tag"; tagId: number }
  | { kind: "unfollow" };

function bulkActionVerb(action: BulkAction): string {
  switch (action.kind) {
    case "favorite":
      return action.value ? "favourited" : "unfavourited";
    case "reading_status":
      return action.value === "completed" ? "marked read" : `marked ${action.value}`;
    case "tag":
      return "tagged";
    case "unfollow":
      return "unfollowed";
  }
}

function bulkActionRequest(
  action: BulkAction,
  series: FollowedSeries,
): Promise<unknown> {
  const ref: SeriesId = {
    sourceId: series.source_id,
    seriesKey: series.series_key,
  };
  switch (action.kind) {
    case "favorite":
      return libraryApi.patchSeries(series.id, { is_favorite: action.value });
    case "reading_status":
      return libraryApi.patchSeries(series.id, { reading_status: action.value });
    case "tag":
      return libraryApi.addTagToSeries(ref, action.tagId);
    case "unfollow":
      return libraryApi.unfollow(series.id);
  }
}

export interface BulkActionState {
  run: (
    action: BulkAction,
    series: readonly FollowedSeries[],
  ) => Promise<BulkOutcome<FollowedSeries>>;
  cancel: () => void;
  progress: BulkProgress | null;
  isRunning: boolean;
  message: string | null;
  dismissMessage: () => void;
}

export function useBulkSeriesAction(): BulkActionState {
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<BulkProgress | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => abortRef.current?.abort(), []);
  const dismissMessage = useCallback(() => setMessage(null), []);

  const run = useCallback(
    async (action: BulkAction, series: readonly FollowedSeries[]) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setIsRunning(true);
      setMessage(null);
      setProgress({ completed: 0, failed: 0, total: series.length });

      try {
        const outcome = await runBulk(
          series,
          (row) => bulkActionRequest(action, row),
          { onProgress: setProgress, signal: controller.signal },
        );
        await queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });
        setMessage(summarizeBulkOutcome(outcome, bulkActionVerb(action)));
        return outcome;
      } finally {
        abortRef.current = null;
        setIsRunning(false);
        setProgress(null);
      }
    },
    [queryClient],
  );

  return { run, cancel, progress, isRunning, message, dismissMessage };
}
