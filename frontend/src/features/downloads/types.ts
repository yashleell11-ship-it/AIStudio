export interface DownloadItem {
  id: number;
  source: string;
  series_id: string;
  chapter_id: string;
  series_title: string;
  chapter_title: string;
  status: string;
  progress: number;
  pages_done: number;
  pages_total: number;
  bytes_downloaded: number;
  speed_bps: number | null;
  speed_mbps: number | null;
  eta_seconds: number | null;
  local_chapter_id: number | null;
  created_at: string;
  updated_at: string;
  error: string | null;
  priority: number;
  queue_state: string | null;
  retry_count: number;
}

export interface QueueDownloadResponse {
  queued: number[];
  skipped: string[];
}

export interface BulkActionResponse {
  affected: number;
}

export interface DownloadMetrics {
  total: number;
  completed: number;
  failed: number;
  remaining: number;
  active: number;
  queued: number;
  paused: number;
  storage_used_bytes: number;
  storage_free_bytes: number;
  overall_speed_bps: number;
  overall_speed_mbps: number;
  overall_eta_seconds: number | null;
  workers: {
    configured: number;
    active: number;
    running: number;
  };
}

export interface SeriesDownloadGroup {
  key: string;
  source: string;
  series_id: string;
  series_title: string;
  items: DownloadItem[];
  active: number;
  queued: number;
  completed: number;
  failed: number;
  paused: number;
}

export interface DownloadSettings {
  download_concurrent_chapters: number;
  download_page_concurrency: number;
  download_retry_count: number;
  download_retry_delay_seconds: number;
  download_timeout_seconds: number;
  active_download_count: number;
}

export type DownloadSettingsUpdate = Partial<
  Omit<DownloadSettings, "active_download_count">
>;
