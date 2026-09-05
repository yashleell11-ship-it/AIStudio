import { describe, expect, it } from "vitest";
import {
  notificationChapterRef,
  toSettingsUpdatePayload,
} from "./notification-link";
import type { UpdateNotification, UpdateSettings } from "./types";

function notification(
  overrides: Partial<UpdateNotification> = {},
): UpdateNotification {
  return {
    id: 1,
    followed_series_id: 4,
    source_id: "asura",
    series_key: "nano-machine",
    chapter_key: "ch-210",
    chapter_title: "Chapter 210",
    chapter_number: 210,
    is_read: false,
    created_at: null,
    ...overrides,
  };
}

describe("notificationChapterRef", () => {
  it("names the chapter source-natively, leaving the reader choice to the caller", () => {
    expect(notificationChapterRef(notification())).toEqual({
      sourceId: "asura",
      seriesKey: "nano-machine",
      chapterKey: "ch-210",
    });
  });

  it("passes opaque keys through untouched, escaping nothing", () => {
    // Encoding belongs to the link builders (`readerChapterHref` /
    // `novelChapterHref`); a ref that pre-escaped would be double-encoded.
    expect(
      notificationChapterRef(
        notification({ series_key: "a/b", chapter_key: "vol/1/ch/2" }),
      ),
    ).toEqual({ sourceId: "asura", seriesKey: "a/b", chapterKey: "vol/1/ch/2" });
  });
});

describe("toSettingsUpdatePayload", () => {
  const settings: UpdateSettings = {
    enabled: true,
    check_interval_minutes: 45,
    notify_enabled: false,
    check_on_startup: true,
    last_run_at: "2026-09-03T00:00:00Z",
  };

  it("sends exactly the four writable fields", () => {
    expect(toSettingsUpdatePayload(settings)).toEqual({
      enabled: true,
      check_interval_minutes: 45,
      notify_enabled: false,
      check_on_startup: true,
    });
  });

  it("never includes auto_download (dropped in 1a) or the server-owned last_run_at", () => {
    const payload = toSettingsUpdatePayload(settings) as Record<string, unknown>;
    expect("auto_download" in payload).toBe(false);
    expect("auto_download_enabled" in payload).toBe(false);
    expect("last_run_at" in payload).toBe(false);
  });
});
