import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { updatesApi } from "./api";

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

export function useUnfollowTracker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updatesApi.unfollow,
    onSuccess: () => {
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
