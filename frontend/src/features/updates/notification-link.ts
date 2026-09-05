import type { ChapterId } from "@/types/api";
import type { UpdateNotification, UpdateSettings } from "./types";

/**
 * The chapter a "new chapter" notification points at.
 *
 * A ref, not a URL: this row used to build `/reader/...` unconditionally, which
 * opened the PAGE reader for a novel and rendered "This chapter has no pages."
 * — the follow → notify → read loop dead-ended on an error page for every web
 * novel followed. Every other screen that can list a novel row resolves its
 * link through `useChapterHref`, and now so does this one.
 */
export function notificationChapterRef(item: UpdateNotification): ChapterId {
  return {
    sourceId: item.source_id,
    seriesKey: item.series_key,
    chapterKey: item.chapter_key,
  };
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
