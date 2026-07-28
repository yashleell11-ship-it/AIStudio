/**
 * Shapes exchanged with the service worker.
 *
 * These mirror the records `public/sw.js` writes into its per-profile index.
 * They are declared here rather than inferred because the worker is plain
 * JavaScript outside the TypeScript program: this file is the contract, and
 * `policy-contract.test.ts` checks the half of it that is decidable from the
 * worker's own source.
 */

export type SavedChapterStatus =
  /** Fetching pages right now. */
  | "saving"
  /** Every page is on the device. */
  | "ready"
  /** Interrupted or a page failed — readable, but with holes. */
  | "partial"
  /** Stopped because the device is out of room, not because of an error. */
  | "paused";

export interface SavedChapterEntry {
  /** Unique within a profile's cache; see `chapterCacheKey`. */
  key: string;
  chapterId: string;
  seriesId: string;
  title: string;
  seriesTitle: string | null;
  pageCount: number;
  payloadUrl: string;
  /** Everything this chapter put in the cache, so removal takes exactly it. */
  urls: string[];
  savedPages: number;
  bytes: number;
  status: SavedChapterStatus;
  /** Pages that could not be fetched. A non-zero count means holes. */
  failed: number;
  /** The server's page ids moved since this was saved — save it again. */
  stale: boolean;
  savedAt: number;
  lastOpenedAt: number | null;
  /**
   * When the chapter was FINISHED — the start of the 2-day deletion timer.
   * `null` means "not finished", which is also what reopening it resets it to,
   * so a re-read cancels its own expiry.
   */
  readAt: number | null;
}

export interface StorageEstimateSnapshot {
  usage: number;
  quota: number;
}

/** What the worker reports. Rebuilt per client, in that client's scope. */
export interface OfflineWorkerState {
  scopeToken: string | null;
  entries: SavedChapterEntry[];
  retentionMs: number | null;
  estimate: StorageEstimateSnapshot | null;
  openChapterKey: string | null;
}

export type OfflineReadiness =
  /** Still deciding — no answer from the worker yet. */
  | "pending"
  /** The worker is live and has answered. */
  | "ready"
  /** No service worker in this browser, or the page is not secure. */
  | "unsupported"
  /** Supported, but there is no active reading profile to save under. */
  | "unscoped";

export interface OfflineState extends OfflineWorkerState {
  readiness: OfflineReadiness;
}
