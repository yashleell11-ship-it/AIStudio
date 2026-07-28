import { http } from "@/services/http";
import type {
  MigrateTrackerRequest,
  MigrationCandidatesResponse,
  MigrationPlan,
  SeriesTracker,
  UpdateNotification,
  UpdateRun,
  UpdateSettings,
  UpdateSource,
} from "./types";

export const updatesApi = {
  settings: () => http.get<UpdateSettings>("/updates/settings"),

  updateSettings: (body: Partial<UpdateSettings>) =>
    http.put<UpdateSettings>("/updates/settings", body),

  sources: () => http.get<UpdateSource[]>("/updates/sources"),

  trackers: (params?: { track_kind?: string; source?: string }) =>
    http.get<SeriesTracker[]>("/updates/trackers", { query: params }),

  follow: (body: { source: string; series_id: string; series_title: string }) =>
    http.post<SeriesTracker>("/updates/trackers/follow", body),

  updateTracker: (trackerId: number, body: Partial<SeriesTracker>) =>
    http.patch<SeriesTracker>(`/updates/trackers/${trackerId}`, body),

  unfollow: (trackerId: number) =>
    http.delete<{ deleted: boolean }>(`/updates/trackers/${trackerId}`),

  migrationCandidates: (
    trackerId: number,
    params?: { q?: string; per_page?: number },
  ) =>
    http.get<MigrationCandidatesResponse>(
      `/updates/trackers/${trackerId}/migration-candidates`,
      { query: params },
    ),

  // Preview and commit are the same call; `dry_run` decides whether anything
  // is written. Both return the identical shape.
  migrateTracker: (trackerId: number, body: MigrateTrackerRequest) =>
    http.post<MigrationPlan>(`/updates/trackers/${trackerId}/migrate`, body),

  syncDownloaded: () =>
    http.post<{ created: number; updated: number; total: number }>(
      "/updates/trackers/sync-downloaded",
    ),

  notifications: (params?: { unread_only?: boolean; limit?: number }) =>
    http.get<UpdateNotification[]>("/updates/notifications", { query: params }),

  unreadCount: () => http.get<{ count: number }>("/updates/notifications/unread-count"),

  markRead: (notificationId: number) =>
    http.patch<UpdateNotification>(`/updates/notifications/${notificationId}/read`),

  markAllRead: () => http.post<{ marked_read: number }>("/updates/notifications/read-all"),

  runs: (limit?: number) =>
    http.get<UpdateRun[]>("/updates/runs", { query: limit ? { limit } : undefined }),

  check: (body?: { tracker_ids?: number[] }) => http.post<UpdateRun | { queued: boolean }>(
    "/updates/check",
    body ?? {},
  ),

  checkTracker: (trackerId: number) =>
    http.post<{ tracker_id: number; new_chapters: number; tracker: SeriesTracker }>(
      `/updates/trackers/${trackerId}/check`,
    ),
};
