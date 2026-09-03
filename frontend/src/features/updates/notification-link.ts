import { readerChapterHref } from "@/features/reader/reader-link";
import type { UpdateNotification, UpdateSettings } from "./types";

/** The reader URL a "new chapter" notification deep-links to. */
export function notificationReaderHref(item: UpdateNotification): string {
  return readerChapterHref({
    sourceId: item.source_id,
    seriesKey: item.series_key,
    chapterKey: item.chapter_key,
  });
}

/**
 * The body sent to `PUT /updates/settings`. Explicitly the four writable
 * fields — 1a dropped `auto_download`, and `last_run_at` is server-owned.
 */
export function toSettingsUpdatePayload(
  draft: UpdateSettings,
): Pick<
  UpdateSettings,
  "enabled" | "check_interval_minutes" | "notify_enabled" | "check_on_startup"
> {
  return {
    enabled: draft.enabled,
    check_interval_minutes: draft.check_interval_minutes,
    notify_enabled: draft.notify_enabled,
    check_on_startup: draft.check_on_startup,
  };
}
