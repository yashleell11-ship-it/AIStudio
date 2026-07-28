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

// ---------------------------------------------------------------------------
// Queue state: the six statuses the backend actually writes, what each one
// means, and which actions the API will accept for it.
//
// Every status below is written somewhere in backend/services/download_manager.py
// or backend/services/download_service.py; there is no seventh. Keeping the
// list closed here is what lets the view render an honest badge for each row
// instead of title-casing whatever string arrived.
// ---------------------------------------------------------------------------

export type DownloadStatus =
  | "queued"
  | "downloading"
  | "paused"
  | "failed"
  | "completed"
  | "cancelled";

export type DownloadStatusTone =
  | "active"
  | "pending"
  | "paused"
  | "failed"
  | "done"
  | "neutral";

export interface DownloadStatusDescriptor {
  status: string;
  label: string;
  tone: DownloadStatusTone;
  /** One line explaining what this state means for the chapter. */
  description: string;
}

const STATUS_DESCRIPTORS: Record<DownloadStatus, Omit<DownloadStatusDescriptor, "status">> = {
  downloading: {
    label: "Downloading",
    tone: "active",
    description: "Pages are transferring right now.",
  },
  queued: {
    label: "Queued",
    tone: "pending",
    description: "Waiting for a free download worker.",
  },
  paused: {
    label: "Paused",
    tone: "paused",
    description: "Held by you; resume to put it back in the queue.",
  },
  failed: {
    label: "Failed",
    tone: "failed",
    description: "The download stopped with an error and will not retry itself.",
  },
  completed: {
    label: "Completed",
    tone: "done",
    description: "Imported into the local library.",
  },
  cancelled: {
    label: "Cancelled",
    tone: "neutral",
    description: "Removed from the queue before it finished.",
  },
};

/**
 * Label, tone, and meaning for one download status. An unrecognised status is
 * reported as-is rather than guessed at, so a backend that grows a new state
 * shows up as an obvious unknown instead of being mislabelled.
 */
export function describeDownloadStatus(status: string): DownloadStatusDescriptor {
  const known = STATUS_DESCRIPTORS[status as DownloadStatus];
  if (known) {
    return { status, ...known };
  }
  return {
    status,
    label: status || "Unknown",
    tone: "neutral",
    description: "Reported by the server but not recognised by this client.",
  };
}

// The action predicates below mirror the server's own state checks exactly, so
// a disabled button means "the API would reject this", not a guess:
//   retry  -> failed | paused          (download_service.retry)
//   resume -> paused | failed          (download_service.resume)
//   pause  -> anything but completed/cancelled, but only queued/downloading
//             work is actually interruptible, so that is what the UI offers
//   cancel -> anything but completed   (already-cancelled excluded here: the
//             API accepts it, but it is a no-op the user cannot see)
//   move   -> queued AND queue_state "pending" (download_service.move_queue_item)

export function canRetryDownload(item: DownloadItem): boolean {
  return item.status === "failed" || item.status === "paused";
}

export function canResumeDownload(item: DownloadItem): boolean {
  return item.status === "paused" || item.status === "failed";
}

export function canPauseDownload(item: DownloadItem): boolean {
  return item.status === "queued" || item.status === "downloading";
}

export function canCancelDownload(item: DownloadItem): boolean {
  return item.status !== "completed" && item.status !== "cancelled";
}

export function canMoveDownload(item: DownloadItem): boolean {
  return item.status === "queued" && item.queue_state === "pending";
}

export interface DownloadPartition {
  downloading: DownloadItem[];
  queued: DownloadItem[];
  paused: DownloadItem[];
  failed: DownloadItem[];
  completed: DownloadItem[];
  cancelled: DownloadItem[];
  /** Anything the backend reported that is none of the above. */
  other: DownloadItem[];
}

function byUpdatedAtDesc(a: DownloadItem, b: DownloadItem): number {
  return b.updated_at.localeCompare(a.updated_at);
}

/**
 * Splits a flat download list into one bucket per status.
 *
 * Failures are sorted newest-first because that is the order the owner reads
 * them in: the most recent error is the one that explains why the queue is
 * stuck now. The other buckets keep the server's order (created_at desc).
 */
export function partitionDownloads(items: DownloadItem[]): DownloadPartition {
  const partition: DownloadPartition = {
    downloading: [],
    queued: [],
    paused: [],
    failed: [],
    completed: [],
    cancelled: [],
    other: [],
  };

  for (const item of items) {
    switch (item.status) {
      case "downloading":
        partition.downloading.push(item);
        break;
      case "queued":
        partition.queued.push(item);
        break;
      case "paused":
        partition.paused.push(item);
        break;
      case "failed":
        partition.failed.push(item);
        break;
      case "completed":
        partition.completed.push(item);
        break;
      case "cancelled":
        partition.cancelled.push(item);
        break;
      default:
        partition.other.push(item);
        break;
    }
  }

  partition.failed.sort(byUpdatedAtDesc);
  return partition;
}

/** One distinct failure message and how many chapters hit it. */
export interface FailureReason {
  message: string;
  count: number;
  /** Chapters that failed with this exact message, newest first. */
  items: DownloadItem[];
}

export interface FailureSummary {
  /** Every failed chapter, newest failure first. */
  items: DownloadItem[];
  count: number;
  /** How many distinct series the failures span. */
  seriesCount: number;
  /** Ids the retry endpoint will accept, newest first. */
  retriableIds: number[];
  /**
   * Failures collapsed by error message. A dead connector fails every chapter
   * of a series with the same string, so this turns forty identical rows into
   * one line the owner can actually read.
   */
  reasons: FailureReason[];
}

/** Placeholder used when the backend recorded a failure with no error text. */
export const UNKNOWN_FAILURE_MESSAGE = "No error message was recorded.";

export function summarizeFailures(items: DownloadItem[]): FailureSummary {
  const failed = partitionDownloads(items).failed;
  const reasons = new Map<string, FailureReason>();

  for (const item of failed) {
    const message = item.error?.trim() || UNKNOWN_FAILURE_MESSAGE;
    const reason = reasons.get(message);
    if (reason) {
      reason.count += 1;
      reason.items.push(item);
    } else {
      reasons.set(message, { message, count: 1, items: [item] });
    }
  }

  return {
    items: failed,
    count: failed.length,
    seriesCount: new Set(failed.map((item) => seriesGroupKey(item.source, item.series_id))).size,
    retriableIds: failed.filter(canRetryDownload).map((item) => item.id),
    reasons: Array.from(reasons.values()).sort(
      (a, b) => b.count - a.count || a.message.localeCompare(b.message),
    ),
  };
}
