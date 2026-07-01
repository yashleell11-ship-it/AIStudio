export type TrackKind = "followed" | "downloaded";

export interface UpdateSettings {
  enabled: boolean;
  check_interval_minutes: number;
  notify_enabled: boolean;
  auto_download_enabled: boolean;
  check_on_startup: boolean;
  last_run_at: string | null;
  updated_at: string | null;
}

export interface SeriesTracker {
  id: number;
  source: string;
  series_id: string;
  series_title: string;
  track_kind: TrackKind;
  local_series_id: number | null;
  enabled: boolean;
  notify: boolean;
  auto_download: boolean;
  check_interval_minutes: number | null;
  known_chapter_count: number;
  last_checked_at: string | null;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface UpdateNotification {
  id: number;
  tracker_id: number;
  source: string;
  series_id: string;
  series_title: string;
  chapter_id: string;
  chapter_title: string;
  chapter_number: number | null;
  is_read: boolean;
  created_at: string | null;
}

export interface UpdateRun {
  id: number;
  trigger: string;
  status: string;
  series_checked: number;
  new_chapters_found: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface UpdateSource {
  source_type: string;
  name: string;
}
