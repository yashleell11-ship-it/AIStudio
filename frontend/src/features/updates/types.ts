/**
 * The update system is source-native now (spec §3.6). Following a series lives
 * at `POST /library/follow`; this feature is purely the update-check settings,
 * the notifications a check produces, and the run log. There are no trackers and
 * no source-migration surface.
 */

export interface UpdateSettings {
  enabled: boolean;
  check_interval_minutes: number;
  notify_enabled: boolean;
  check_on_startup: boolean;
  last_run_at: string | null;
}

/** One new-chapter notification (backend/services/update_service.py:serialize_notification). */
export interface UpdateNotification {
  id: number;
  followed_series_id: number | null;
  source_id: string;
  series_key: string;
  chapter_key: string;
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
