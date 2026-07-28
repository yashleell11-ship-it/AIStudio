import type { StorageScope } from "@/lib/scoped-storage";
import type { OfflineWorkerState } from "./types";

/**
 * The page ↔ service worker message contract.
 *
 * The worker is the ONLY writer of Cache Storage. The page reads its state and
 * asks for changes; it never opens a cache itself. That is what keeps the
 * per-profile isolation checkable in one place: there is exactly one piece of
 * code that decides which cache a byte goes into, and it derives the name from
 * a scope it was handed rather than from anything in the request.
 */

export const OFFLINE_MESSAGE = {
  setScope: "mm-offline/set-scope",
  getState: "mm-offline/get-state",
  saveChapter: "mm-offline/save-chapter",
  cancelSave: "mm-offline/cancel-save",
  removeChapter: "mm-offline/remove-chapter",
  markOpened: "mm-offline/mark-opened",
  markFinished: "mm-offline/mark-finished",
  chapterClosed: "mm-offline/chapter-closed",
  sweep: "mm-offline/sweep",
  setRetention: "mm-offline/set-retention",
  clearScope: "mm-offline/clear-scope",
  skipWaiting: "mm-offline/skip-waiting",
} as const;

/** Pushed by the worker whenever its index changes. */
export const OFFLINE_STATE_EVENT = "mm-offline/state";

/** One chapter's download plan, resolved to absolute URLs by the page. */
export interface SaveChapterRequest {
  key: string;
  chapterId: string;
  seriesId: string;
  title: string;
  seriesTitle: string | null;
  scope: StorageScope;
  profileId: number;
  /** The reader route, so a cold offline start has a document to render. */
  documentUrl: string;
  /** The chapter payload endpoint — the cache key its JSON is stored under. */
  payloadUrl: string;
  /** That payload's body, when the page already has it. */
  payloadJson: string | null;
  /** Page images, in page order. */
  imageUrls: string[];
  /** Small supporting GETs (the payload itself, adjacency). */
  extraUrls: string[];
}

export interface OfflineReply {
  ok: boolean;
  reason?: string;
  state?: OfflineWorkerState;
  removed?: number;
}

export interface OfflineStateMessage {
  type: typeof OFFLINE_STATE_EVENT;
  state: OfflineWorkerState;
}

export function isOfflineStateMessage(value: unknown): value is OfflineStateMessage {
  if (!value || typeof value !== "object") return false;
  const message = value as { type?: unknown; state?: unknown };
  return (
    message.type === OFFLINE_STATE_EVENT &&
    typeof message.state === "object" &&
    message.state !== null
  );
}
