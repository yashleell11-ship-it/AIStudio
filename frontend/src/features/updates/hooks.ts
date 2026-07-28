import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { remapSourceSeriesProgress } from "@/features/sources/source-progress";
import { updatesApi } from "./api";
import type {
  MigrateTrackerRequest,
  SeriesTracker,
  UpdateNotification,
} from "./types";

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

/**
 * Sources the update checker can track. Filtered by the caller's 18+ gate
 * server-side, and the registry cannot change without a restart, so it is
 * cached aggressively.
 */
export function useUpdateSources() {
  return useQuery({
    queryKey: [...UPDATES_KEY, "sources"],
    queryFn: () => updatesApi.sources(),
    staleTime: 5 * 60_000,
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

// --- Source migration ---

/**
 * Candidate targets for repointing a followed series.
 *
 * Backed by the federated search fan-out, so it is slow and best fetched only
 * while the migration dialog is open — hence the explicit `enabled` flag. It
 * inherits the fan-out's partial-failure semantics: a large `sources_failed` is
 * routine, not an error.
 */
export function useMigrationCandidates(
  trackerId: number,
  query: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: [...UPDATES_KEY, "migration-candidates", trackerId, query],
    queryFn: () => updatesApi.migrationCandidates(trackerId, { q: query || undefined }),
    enabled,
    // A fan-out across every source is far too expensive to refetch on a whim.
    staleTime: 5 * 60_000,
  });
}

/**
 * Preview or perform a source migration.
 *
 * On a real (non-dry-run) migration the returned `chapter_map` is replayed over
 * the local online-progress store before anything else: progress for a remote
 * series lives only in the browser, so the server cannot move it and a commit
 * that skipped this step would silently reset the user's place. Trackers and
 * notifications are then refetched, since both were rewritten server-side.
 */
export function useMigrateTracker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      trackerId,
      body,
    }: {
      trackerId: number;
      body: MigrateTrackerRequest;
    }) => updatesApi.migrateTracker(trackerId, body),
    onSuccess: (plan) => {
      if (!plan.applied) {
        return;
      }
      remapSourceSeriesProgress(
        { source: plan.from.source, seriesId: plan.from.series_id },
        { source: plan.to.source, seriesId: plan.to.series_id },
        plan.chapter_map,
      );
      void queryClient.invalidateQueries({ queryKey: [...UPDATES_KEY, "trackers"] });
      void queryClient.invalidateQueries({
        queryKey: [...UPDATES_KEY, "notifications"],
      });
    },
  });
}

export interface NewChaptersBannerState {
  /** Whether the banner should be visible right now. */
  show: boolean;
  /** Number of unread new-chapter notifications. */
  count: number;
  /** Distinct series those notifications span. */
  seriesCount: number;
  /** Highest notification id currently unread, or null when there are none. */
  latestId: number | null;
}

/**
 * Pure visibility selector for the new-chapters banner. Exported for unit
 * testing (no React renderer needed — same style as {@link findFollowedTracker}).
 *
 * The banner shows when there is at least one unread notification whose id is
 * newer than the last dismissal watermark. Because notification ids are
 * monotonic, dismissing hides the banner until a genuinely newer chapter
 * arrives, at which point it reappears.
 */
export function computeNewChaptersBanner(
  notifications: UpdateNotification[] | undefined,
  dismissedMaxId: number | null,
): NewChaptersBannerState {
  const unread = notifications ?? [];
  const count = unread.length;
  if (count === 0) {
    return { show: false, count: 0, seriesCount: 0, latestId: null };
  }
  const latestId = unread.reduce((max, n) => (n.id > max ? n.id : max), unread[0].id);
  const seriesCount = new Set(unread.map((n) => n.series_id)).size;
  const show = dismissedMaxId === null || latestId > dismissedMaxId;
  return { show, count, seriesCount, latestId };
}
