import type { DownloadItem, SeriesDownloadGroup } from "./types";

export function seriesGroupKey(source: string, seriesId: string): string {
  return `${source}::${seriesId}`;
}

/**
 * Groups a flat download list by (source, series_id). Purely client-side --
 * the backend already scopes its series-level pause/resume/cancel endpoints
 * by (source, series_id), so grouping here just needs to match that same key.
 */
export function groupDownloadsBySeries(items: DownloadItem[]): SeriesDownloadGroup[] {
  const groups = new Map<string, SeriesDownloadGroup>();

  for (const item of items) {
    const key = seriesGroupKey(item.source, item.series_id);
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        source: item.source,
        series_id: item.series_id,
        series_title: item.series_title,
        items: [],
        active: 0,
        queued: 0,
        completed: 0,
        failed: 0,
        paused: 0,
      };
      groups.set(key, group);
    }
    group.items.push(item);
    switch (item.status) {
      case "downloading":
        group.active += 1;
        break;
      case "queued":
        group.queued += 1;
        break;
      case "completed":
        group.completed += 1;
        break;
      case "failed":
        group.failed += 1;
        break;
      case "paused":
        group.paused += 1;
        break;
      default:
        break;
    }
  }

  return Array.from(groups.values()).sort((a, b) => {
    const aHasWork = a.active + a.queued > 0 ? 0 : 1;
    const bHasWork = b.active + b.queued > 0 ? 0 : 1;
    if (aHasWork !== bHasWork) return aHasWork - bHasWork;
    return a.series_title.localeCompare(b.series_title);
  });
}

export function seriesCanPause(group: SeriesDownloadGroup): boolean {
  return group.active + group.queued > 0;
}

export function seriesCanResume(group: SeriesDownloadGroup): boolean {
  return group.paused > 0 || group.failed > 0;
}

export function seriesCanCancel(group: SeriesDownloadGroup): boolean {
  return group.items.some(
    (item) => item.status !== "completed" && item.status !== "cancelled",
  );
}

// Completed chapters are already in the library, and cancelled ones were
// explicitly dismissed -- neither needs a row in the active queue view.
// group.completed/group.items still count them for the header stats; this
// only controls which rows actually render.
const HIDDEN_FROM_QUEUE_VIEW = new Set(["completed", "cancelled"]);

const STATUS_ROW_PRIORITY: Record<string, number> = {
  downloading: 0,
  queued: 1,
  paused: 2,
  failed: 3,
};

/**
 * The chapter rows to actually render for a series: completed/cancelled
 * chapters dropped, and whatever remains sorted so the chapter currently
 * downloading is always first, not buried under older queued entries.
 */
export function visibleGroupItems(group: SeriesDownloadGroup): DownloadItem[] {
  return group.items
    .filter((item) => !HIDDEN_FROM_QUEUE_VIEW.has(item.status))
    .sort((a, b) => {
      const priorityA = STATUS_ROW_PRIORITY[a.status] ?? 99;
      const priorityB = STATUS_ROW_PRIORITY[b.status] ?? 99;
      return priorityA - priorityB;
    });
}
