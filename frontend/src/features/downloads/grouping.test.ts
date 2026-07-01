import { describe, expect, it } from "vitest";
import {
  groupDownloadsBySeries,
  seriesCanCancel,
  seriesCanPause,
  seriesCanResume,
  seriesGroupKey,
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
