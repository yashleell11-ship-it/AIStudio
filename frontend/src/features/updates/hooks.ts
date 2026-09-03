import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { updatesApi } from "./api";
import type { UpdateNotification } from "./types";

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
      void queryClient.invalidateQueries({
        queryKey: [...UPDATES_KEY, "settings"],
      });
    },
  });
}

export function useUpdateNotifications(unreadOnly = false) {
  return useQuery({
    queryKey: [...UPDATES_KEY, "notifications", unreadOnly ? "unread" : "all"],
    queryFn: () =>
      updatesApi.notifications({ unread_only: unreadOnly, limit: 100 }),
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

export function useCheckFollowed() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (followedId: number) => updatesApi.checkFollowed(followedId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: UPDATES_KEY });
    },
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.markRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...UPDATES_KEY, "notifications"],
      });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.markAllRead,
    onSuccess: () => {
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
 * testing (no React renderer needed).
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
  const latestId = unread.reduce(
    (max, n) => (n.id > max ? n.id : max),
    unread[0].id,
  );
  const seriesCount = new Set(
    unread.map((n) => `${n.source_id}:${n.series_key}`),
  ).size;
  const show = dismissedMaxId === null || latestId > dismissedMaxId;
  return { show, count, seriesCount, latestId };
}
