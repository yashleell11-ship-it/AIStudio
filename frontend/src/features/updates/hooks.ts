import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { updatesApi } from "./api";
import type { SeriesTracker } from "./types";

const UPDATES_KEY = ["updates"] as const;

export function useUpdateSettings() {
  return useQuery({
    queryKey: [...UPDATES_KEY, "settings"],
    queryFn: () => updatesApi.settings(),
  });
}

export function useUpdateSettingsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.updateSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...UPDATES_KEY, "settings"] });
    },
  });
}

export function useTrackers(trackKind?: string) {
  return useQuery({
    queryKey: [...UPDATES_KEY, "trackers", trackKind ?? "all"],
    queryFn: () => updatesApi.trackers(trackKind ? { track_kind: trackKind } : undefined),
    refetchInterval: 30_000,
  });
}

export function useUpdateNotifications(unreadOnly = false) {
  return useQuery({
    queryKey: [...UPDATES_KEY, "notifications", unreadOnly ? "unread" : "all"],
    queryFn: () => updatesApi.notifications({ unread_only: unreadOnly, limit: 100 }),
    refetchInterval: 15_000,
  });
}

export function useUnreadNotificationCount() {
  return useQuery({
    queryKey: [...UPDATES_KEY, "notifications", "count"],
    queryFn: () => updatesApi.unreadCount(),
    refetchInterval: 15_000,
  });
}

export function useUpdateRuns() {
  return useQuery({
    queryKey: [...UPDATES_KEY, "runs"],
    queryFn: () => updatesApi.runs(20),
    refetchInterval: 10_000,
  });
}

export function useManualCheck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.check,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: UPDATES_KEY });
    },
  });
}

export function useSyncDownloaded() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.syncDownloaded,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...UPDATES_KEY, "trackers"] });
    },
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.markRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...UPDATES_KEY, "notifications"] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.markAllRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...UPDATES_KEY, "notifications"] });
    },
  });
}

/** Pure lookup used by {@link useFollowedTracker} -- exported for unit testing. */
export function findFollowedTracker(
  trackers: SeriesTracker[] | undefined,
  sourceId: string,
  seriesId: string,
): SeriesTracker | undefined {
  return trackers?.find(
    (tracker) => tracker.source === sourceId && tracker.series_id === seriesId,
  );
}

/**
 * Returns the tracker row for the given source+series if the user is
 * currently following it, else undefined. Drives the Follow/Unfollow button
 * state on source series detail.
 *
 * Derives from the exact same `useTrackers("followed")` cache used
 * everywhere else (e.g. the Updates page) instead of its own query, so a
 * follow/unfollow mutation that patches that cache is reflected here on the
 * very next render -- there is no second cache that can go stale.
 */
export function useFollowedTracker(sourceId: string, seriesId: string) {
  const followed = useTrackers("followed");
  return findFollowedTracker(followed.data, sourceId, seriesId);
}

/**
 * Follow a source series. The follow endpoint returns the new tracker row,
 * so we can patch it straight into the followed-trackers cache for instant
 * feedback without waiting for a refetch. Falls back to invalidation if no
 * cache is present yet.
 */
export function useFollowSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.follow,
    onSuccess: (tracker) => {
      const keys = [
        [...UPDATES_KEY, "trackers", "all"],
        [...UPDATES_KEY, "trackers", "followed"],
      ];
      for (const key of keys) {
        const previous = queryClient.getQueryData<SeriesTracker[]>(key);
        if (!previous) {
          void queryClient.invalidateQueries({ queryKey: key });
          continue;
        }
        if (previous.some((t) => t.id === tracker.id)) continue;
        queryClient.setQueryData<SeriesTracker[]>(key, [...previous, tracker]);
      }
    },
  });
}

export function useUnfollowTracker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.unfollow,
    onMutate: async (trackerId: number) => {
      const keys = [
        [...UPDATES_KEY, "trackers", "all"],
        [...UPDATES_KEY, "trackers", "followed"],
      ];
      const snapshots: Record<string, SeriesTracker[] | undefined> = {};
      for (const key of keys) {
        await queryClient.cancelQueries({ queryKey: key });
        snapshots[key.join(".")] = queryClient.getQueryData<SeriesTracker[]>(key);
        queryClient.setQueryData<SeriesTracker[]>(key, (previous) =>
          previous ? previous.filter((t) => t.id !== trackerId) : previous,
        );
      }
      return { snapshots };
    },
    onError: (_error, _trackerId, context) => {
      if (!context) return;
      for (const [joined, snapshot] of Object.entries(context.snapshots)) {
        queryClient.setQueryData<SeriesTracker[] | undefined>(
          joined.split("."),
          snapshot,
        );
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: [...UPDATES_KEY, "trackers"] });
    },
  });
}

export function useUpdateTracker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof updatesApi.updateTracker>[1] }) =>
      updatesApi.updateTracker(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...UPDATES_KEY, "trackers"] });
    },
  });
}
