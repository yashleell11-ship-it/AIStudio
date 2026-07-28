import { describe, expect, it } from "vitest";
import {
  UNKNOWN_FAILURE_MESSAGE,
  canCancelDownload,
  canMoveDownload,
  canPauseDownload,
  canResumeDownload,
  canRetryDownload,
  describeDownloadStatus,
  groupDownloadsBySeries,
  partitionDownloads,
  seriesCanCancel,
  seriesCanPause,
  seriesCanResume,
  seriesGroupKey,
  summarizeFailures,
  visibleGroupItems,
} from "./grouping";
import type { DownloadItem } from "./types";

function item(overrides: Partial<DownloadItem> = {}): DownloadItem {
  return {
    id: 1,
    source: "mangadex",
    series_id: "series-1",
    chapter_id: "c1",
    series_title: "Solo Leveling",
    chapter_title: "Chapter 1",
    status: "queued",
    progress: 0,
    pages_done: 0,
    pages_total: 0,
    bytes_downloaded: 0,
    speed_bps: null,
    speed_mbps: null,
    eta_seconds: null,
    local_chapter_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    error: null,
    priority: 0,
    queue_state: "pending",
    retry_count: 0,
    ...overrides,
  };
}

describe("groupDownloadsBySeries", () => {
  it("groups items by (source, series_id), not series_id alone", () => {
    const items = [
      item({ id: 1, source: "mangadex", series_id: "series-1" }),
      item({ id: 2, source: "mangakatana", series_id: "series-1" }),
    ];

    const groups = groupDownloadsBySeries(items);

    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.key).sort()).toEqual(
      [seriesGroupKey("mangadex", "series-1"), seriesGroupKey("mangakatana", "series-1")].sort(),
    );
  });

  it("counts each status bucket correctly within a group", () => {
    const items = [
      item({ id: 1, status: "downloading" }),
      item({ id: 2, status: "queued" }),
      item({ id: 3, status: "queued" }),
      item({ id: 4, status: "completed" }),
      item({ id: 5, status: "failed" }),
      item({ id: 6, status: "paused" }),
    ];

    const [group] = groupDownloadsBySeries(items);

    expect(group.items).toHaveLength(6);
    expect(group.active).toBe(1);
    expect(group.queued).toBe(2);
    expect(group.completed).toBe(1);
    expect(group.failed).toBe(1);
    expect(group.paused).toBe(1);
  });

  it("sorts series with active or queued work before series with none", () => {
    const items = [
      item({ id: 1, series_id: "idle-series", series_title: "Idle Series", status: "completed" }),
      item({ id: 2, series_id: "busy-series", series_title: "Busy Series", status: "downloading" }),
    ];

    const groups = groupDownloadsBySeries(items);

    expect(groups[0].series_id).toBe("busy-series");
    expect(groups[1].series_id).toBe("idle-series");
  });
});

describe("series action availability", () => {
  it("seriesCanPause is true only when something is active or queued", () => {
    const busy = groupDownloadsBySeries([item({ status: "downloading" })])[0];
    const idle = groupDownloadsBySeries([item({ status: "completed" })])[0];
    expect(seriesCanPause(busy)).toBe(true);
    expect(seriesCanPause(idle)).toBe(false);
  });

  it("seriesCanResume is true only when something is paused or failed", () => {
    const paused = groupDownloadsBySeries([item({ status: "paused" })])[0];
    const queued = groupDownloadsBySeries([item({ status: "queued" })])[0];
    expect(seriesCanResume(paused)).toBe(true);
    expect(seriesCanResume(queued)).toBe(false);
  });

  it("seriesCanCancel is false only when everything is completed or cancelled", () => {
    const mixed = groupDownloadsBySeries([
      item({ id: 1, status: "completed" }),
      item({ id: 2, status: "cancelled" }),
    ])[0];
    const withQueued = groupDownloadsBySeries([
      item({ id: 1, status: "completed" }),
      item({ id: 2, status: "queued" }),
    ])[0];
    expect(seriesCanCancel(mixed)).toBe(false);
    expect(seriesCanCancel(withQueued)).toBe(true);
  });
});

describe("visibleGroupItems", () => {
  it("excludes completed and cancelled items", () => {
    const group = groupDownloadsBySeries([
      item({ id: 1, status: "queued" }),
      item({ id: 2, status: "completed" }),
      item({ id: 3, status: "cancelled" }),
    ])[0];

    const rows = visibleGroupItems(group);

    expect(rows.map((r) => r.id)).toEqual([1]);
  });

  it("sorts downloading before queued, paused, and failed", () => {
    const group = groupDownloadsBySeries([
      item({ id: 1, status: "failed" }),
      item({ id: 2, status: "paused" }),
      item({ id: 3, status: "queued" }),
      item({ id: 4, status: "downloading" }),
    ])[0];

    const rows = visibleGroupItems(group);

    expect(rows.map((r) => r.id)).toEqual([4, 3, 2, 1]);
  });

  it("returns an empty array when everything is completed or cancelled", () => {
    const group = groupDownloadsBySeries([
      item({ id: 1, status: "completed" }),
      item({ id: 2, status: "cancelled" }),
    ])[0];

    expect(visibleGroupItems(group)).toEqual([]);
  });
});

describe("partitionDownloads", () => {
  it("puts every backend status in its own bucket", () => {
    const partition = partitionDownloads([
      item({ id: 1, status: "downloading" }),
      item({ id: 2, status: "queued" }),
      item({ id: 3, status: "paused" }),
      item({ id: 4, status: "failed" }),
      item({ id: 5, status: "completed" }),
      item({ id: 6, status: "cancelled" }),
    ]);

    expect(partition.downloading.map((i) => i.id)).toEqual([1]);
    expect(partition.queued.map((i) => i.id)).toEqual([2]);
    expect(partition.paused.map((i) => i.id)).toEqual([3]);
    expect(partition.failed.map((i) => i.id)).toEqual([4]);
    expect(partition.completed.map((i) => i.id)).toEqual([5]);
    expect(partition.cancelled.map((i) => i.id)).toEqual([6]);
    expect(partition.other).toEqual([]);
  });

  it("collects an unrecognised status into `other` rather than dropping it", () => {
    const partition = partitionDownloads([item({ id: 9, status: "teleporting" })]);

    expect(partition.other.map((i) => i.id)).toEqual([9]);
    expect(partition.failed).toEqual([]);
  });

  it("sorts failures newest-first so the freshest error is read first", () => {
    const partition = partitionDownloads([
      item({ id: 1, status: "failed", updated_at: "2026-01-01T00:00:00Z" }),
      item({ id: 2, status: "failed", updated_at: "2026-03-01T00:00:00Z" }),
      item({ id: 3, status: "failed", updated_at: "2026-02-01T00:00:00Z" }),
    ]);

    expect(partition.failed.map((i) => i.id)).toEqual([2, 3, 1]);
  });
});

describe("download action availability", () => {
  it("offers retry only for failed and paused chapters", () => {
    expect(canRetryDownload(item({ status: "failed" }))).toBe(true);
    expect(canRetryDownload(item({ status: "paused" }))).toBe(true);
    expect(canRetryDownload(item({ status: "queued" }))).toBe(false);
    expect(canRetryDownload(item({ status: "completed" }))).toBe(false);
  });

  it("offers resume only for paused and failed chapters", () => {
    expect(canResumeDownload(item({ status: "paused" }))).toBe(true);
    expect(canResumeDownload(item({ status: "failed" }))).toBe(true);
    expect(canResumeDownload(item({ status: "downloading" }))).toBe(false);
  });

  it("offers pause only for work that is actually interruptible", () => {
    expect(canPauseDownload(item({ status: "downloading" }))).toBe(true);
    expect(canPauseDownload(item({ status: "queued" }))).toBe(true);
    expect(canPauseDownload(item({ status: "failed" }))).toBe(false);
    expect(canPauseDownload(item({ status: "completed" }))).toBe(false);
  });

  it("offers cancel for anything not already finished or cancelled", () => {
    expect(canCancelDownload(item({ status: "failed" }))).toBe(true);
    expect(canCancelDownload(item({ status: "queued" }))).toBe(true);
    expect(canCancelDownload(item({ status: "completed" }))).toBe(false);
    expect(canCancelDownload(item({ status: "cancelled" }))).toBe(false);
  });

  it("offers reordering only while a chapter is still pending dispatch", () => {
    expect(canMoveDownload(item({ status: "queued", queue_state: "pending" }))).toBe(true);
    expect(canMoveDownload(item({ status: "queued", queue_state: "active" }))).toBe(false);
    expect(canMoveDownload(item({ status: "downloading", queue_state: "pending" }))).toBe(false);
    expect(canMoveDownload(item({ status: "queued", queue_state: null }))).toBe(false);
  });
});

describe("describeDownloadStatus", () => {
  it("distinguishes queued, downloading, completed, and failed", () => {
    expect(describeDownloadStatus("queued").tone).toBe("pending");
    expect(describeDownloadStatus("downloading").tone).toBe("active");
    expect(describeDownloadStatus("completed").tone).toBe("done");
    expect(describeDownloadStatus("failed").tone).toBe("failed");
    expect(describeDownloadStatus("failed").label).toBe("Failed");
  });

  it("reports an unknown status verbatim instead of guessing a tone", () => {
    const descriptor = describeDownloadStatus("teleporting");
    expect(descriptor.label).toBe("teleporting");
    expect(descriptor.tone).toBe("neutral");
  });
});

describe("summarizeFailures", () => {
  it("is empty when nothing failed", () => {
    const summary = summarizeFailures([item({ status: "queued" }), item({ status: "completed" })]);

    expect(summary.count).toBe(0);
    expect(summary.reasons).toEqual([]);
    expect(summary.retriableIds).toEqual([]);
  });

  it("collapses identical errors into one reason with a count", () => {
    const summary = summarizeFailures([
      item({ id: 1, status: "failed", error: "connector timed out" }),
      item({ id: 2, status: "failed", error: "connector timed out" }),
      item({ id: 3, status: "failed", error: "404 from source" }),
    ]);

    expect(summary.count).toBe(3);
    expect(summary.reasons.map((r) => [r.message, r.count])).toEqual([
      ["connector timed out", 2],
      ["404 from source", 1],
    ]);
  });

  it("labels a failure that recorded no error text instead of showing a blank", () => {
    const summary = summarizeFailures([
      item({ id: 1, status: "failed", error: null }),
      item({ id: 2, status: "failed", error: "   " }),
    ]);

    expect(summary.reasons).toHaveLength(1);
    expect(summary.reasons[0].message).toBe(UNKNOWN_FAILURE_MESSAGE);
    expect(summary.reasons[0].count).toBe(2);
  });

  it("counts distinct series by (source, series_id), not title", () => {
    const summary = summarizeFailures([
      item({ id: 1, status: "failed", source: "mangadex", series_id: "s1" }),
      item({ id: 2, status: "failed", source: "mangadex", series_id: "s1" }),
      item({ id: 3, status: "failed", source: "mangakatana", series_id: "s1" }),
    ]);

    expect(summary.seriesCount).toBe(2);
  });

  it("lists every failed id as retriable, newest first", () => {
    const summary = summarizeFailures([
      item({ id: 1, status: "failed", updated_at: "2026-01-01T00:00:00Z" }),
      item({ id: 2, status: "failed", updated_at: "2026-02-01T00:00:00Z" }),
      item({ id: 3, status: "queued" }),
    ]);

    expect(summary.retriableIds).toEqual([2, 1]);
  });
});
