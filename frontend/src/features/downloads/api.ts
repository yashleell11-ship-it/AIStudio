import { http } from "@/services/http";
import type {
  BulkActionResponse,
  DownloadItem,
  DownloadMetrics,
  DownloadSettings,
  DownloadSettingsUpdate,
  QueueDownloadResponse,
} from "./types";

export const downloadsApi = {
  list: () => http.get<DownloadItem[]>("/downloads"),

  metrics: () => http.get<DownloadMetrics>("/downloads/metrics"),

  queueChapters: (body: {
    source_id: string;
    series_id: string;
    chapter_ids: string[];
    series_title?: string;
    chapter_titles?: Record<string, string>;
    priority?: number;
  }) => http.post<QueueDownloadResponse>("/downloads/chapters", body),

  queueSeries: (body: { source_id: string; series_id: string; priority?: number }) =>
    http.post<QueueDownloadResponse>("/downloads/series", body),

  pause: (downloadId: number) =>
    http.post<DownloadItem>(`/downloads/${downloadId}/pause`),

  resume: (downloadId: number) =>
    http.post<DownloadItem>(`/downloads/${downloadId}/resume`),

  cancel: (downloadId: number) =>
    http.post<DownloadItem>(`/downloads/${downloadId}/cancel`),

  retry: (downloadId: number) =>
    http.post<DownloadItem>(`/downloads/${downloadId}/retry`),

  pauseSeries: (body: { source_id: string; series_id: string }) =>
    http.post<BulkActionResponse>("/downloads/series/pause", body),

  resumeSeries: (body: { source_id: string; series_id: string }) =>
    http.post<BulkActionResponse>("/downloads/series/resume", body),

  cancelSeries: (body: { source_id: string; series_id: string }) =>
    http.post<BulkActionResponse>("/downloads/series/cancel", body),

  pauseAll: () => http.post<BulkActionResponse>("/downloads/pause-all"),

  resumeAll: () => http.post<BulkActionResponse>("/downloads/resume-all"),

  cancelAll: () => http.post<BulkActionResponse>("/downloads/cancel-all"),

  getSettings: () => http.get<DownloadSettings>("/downloads/settings"),

  updateSettings: (body: DownloadSettingsUpdate) =>
    http.put<DownloadSettings>("/downloads/settings", body),
};
