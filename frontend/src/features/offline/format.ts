import type { SavedChapterEntry, StorageEstimateSnapshot } from "./types";

/** Powers of 1024 with one decimal — how a storage screen has to read. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 MB";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = value >= 100 || unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${units[unit]}`;
}

export function savePercent(entry: SavedChapterEntry): number {
  if (entry.pageCount <= 0) return 0;
  return Math.min(100, Math.round((entry.savedPages / entry.pageCount) * 100));
}

export type EntryTone = "ready" | "busy" | "warn";

export interface EntryDescription {
  label: string;
  tone: EntryTone;
}

/**
 * One line describing a saved chapter's real state.
 *
 * "Saved" is only claimed when every page is actually on the device: a chapter
 * that quietly lost four pages would be discovered on a train, which is the one
 * place it cannot be fixed.
 */
export function describeEntry(entry: SavedChapterEntry): EntryDescription {
  if (entry.status === "saving") {
    return { label: `Saving ${entry.savedPages}/${entry.pageCount}`, tone: "busy" };
  }
  if (entry.status === "paused") {
    return { label: "Paused — device is full", tone: "warn" };
  }
  if (entry.stale) {
    return { label: "Pages changed on the server — save again", tone: "warn" };
  }
  if (entry.status === "partial" || entry.savedPages < entry.pageCount) {
    return {
      label: `Incomplete — ${entry.savedPages}/${entry.pageCount} pages`,
      tone: "warn",
    };
  }
  return { label: `${entry.pageCount} pages · ${formatBytes(entry.bytes)}`, tone: "ready" };
}

/** True once every page is present and nothing is outstanding. */
export function isFullySaved(entry: SavedChapterEntry | null | undefined): boolean {
  if (!entry) return false;
  return entry.status === "ready" && entry.savedPages >= entry.pageCount && !entry.stale;
}

/**
 * When this chapter's copy is due to be deleted, or null if nothing is pending.
 * `readAt` is only set on a FINISHED chapter, so an unread one never has a due
 * date however long it has sat there.
 */
export function expiryDueAt(
  entry: SavedChapterEntry,
  retentionMs: number | null,
): number | null {
  if (retentionMs === null || !(retentionMs > 0)) return null;
  if (typeof entry.readAt !== "number" || !(entry.readAt > 0)) return null;
  return entry.readAt + retentionMs;
}

/** Coarse, honest wording: the sweep only runs when the app is opened. */
export function formatDueIn(dueAt: number, now: number): string {
  const remaining = dueAt - now;
  if (remaining <= 0) return "Deletes next time you open the app";
  // Compared before rounding: 30 minutes left rounds to "1 hour", which reads
  // as more time than there is.
  if (remaining < 3_600_000) return "Deletes within the hour";
  const hours = Math.round(remaining / 3_600_000);
  if (hours < 24) return `Deletes in about ${hours} ${hours === 1 ? "hour" : "hours"}`;
  const days = Math.round(hours / 24);
  return `Deletes in about ${days} ${days === 1 ? "day" : "days"}`;
}

export interface SeriesGroup {
  /** `${sourceId}:${seriesKey}` — stable within a profile's saved set. */
  id: string;
  sourceId: string;
  seriesKey: string;
  seriesTitle: string;
  bytes: number;
  entries: SavedChapterEntry[];
}

/**
 * Saved chapters grouped by series, newest series first, chapters inside a
 * series in the order they were saved. A reader thinks in series, not in
 * chapter keys.
 */
export function groupBySeries(entries: SavedChapterEntry[]): SeriesGroup[] {
  const groups = new Map<string, SeriesGroup>();
  for (const entry of entries) {
    const id = `${entry.sourceId}:${entry.seriesKey}`;
    const existing = groups.get(id);
    if (existing) {
      existing.entries.push(entry);
      existing.bytes += entry.bytes;
      continue;
    }
    groups.set(id, {
      id,
      sourceId: entry.sourceId,
      seriesKey: entry.seriesKey,
      seriesTitle: entry.seriesTitle ?? "Unknown series",
      bytes: entry.bytes,
      entries: [entry],
    });
  }
  const list = [...groups.values()];
  for (const group of list) {
    group.entries.sort((a, b) => a.savedAt - b.savedAt);
  }
  list.sort((a, b) => newestSavedAt(b.entries) - newestSavedAt(a.entries));
  return list;
}

function newestSavedAt(entries: SavedChapterEntry[]): number {
  return entries.reduce((max, entry) => Math.max(max, entry.savedAt), 0);
}

export interface StorageSummary {
  /** Bytes this feature is accountable for. */
  chapterBytes: number;
  chapterCount: number;
  /** Everything this origin holds, saved chapters included. */
  usage: number;
  quota: number;
  /** 0-100, or null when the browser will not say. */
  percentUsed: number | null;
  free: number | null;
}

export function summariseStorage(
  entries: SavedChapterEntry[],
  estimate: StorageEstimateSnapshot | null,
): StorageSummary {
  const chapterBytes = entries.reduce((total, entry) => total + (entry.bytes || 0), 0);
  const usable =
    estimate !== null &&
    Number.isFinite(estimate.quota) &&
    Number.isFinite(estimate.usage) &&
    estimate.quota > 0;
  return {
    chapterBytes,
    chapterCount: entries.length,
    usage: usable ? estimate.usage : 0,
    quota: usable ? estimate.quota : 0,
    percentUsed: usable
      ? Math.min(100, Math.round((estimate.usage / estimate.quota) * 100))
      : null,
    free: usable ? Math.max(0, estimate.quota - estimate.usage) : null,
  };
}
