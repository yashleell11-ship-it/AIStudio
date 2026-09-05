/**
 * Offline reading for the web client.
 *
 * A service worker (`public/sw.js`) plus the Cache API give the browser what
 * docs/OFFLINE_READING.md needs five to six weeks of native iOS work to build:
 * chapters that open with the server unreachable. No app store, no certificate,
 * no sideload, and — unlike the phone — no background execution to miss,
 * because the caching happens in the page's own worker while it is open.
 *
 * The pieces:
 *   public/sw-policy.js  every decision that is pure data (unit-tested)
 *   public/sw.js         the network, Cache Storage and client messaging
 *   client.ts            registration, the message channel, the shared store
 *   save-request.ts      an open chapter → the exact URLs to store
 *   session-gate.ts      why an unanswered /auth/me must not redirect to /login
 *   components/          the reader control, the storage screen, registration
 *   use-chapter-picker   a series page's multi-select download, and what it
 *                        already holds (chapter-selection + download-queue)
 *
 * `session-gate.ts` is imported directly by the app shell rather than through
 * this barrel: the shell wraps every page, and this barrel pulls in the storage
 * screen and the reader control with it.
 *
 * Isolation: a saved chapter lives in a cache named for the (user, profile)
 * that saved it, the worker is the only writer, and it takes the scope from
 * what the page published rather than from anything in a request. No scope
 * means no cache — never a shared default.
 */

export {
  ChapterDownloadBar,
  ChapterDownloadTrigger,
} from "./components/ChapterDownloadBar";
export { DownloadChapterControl } from "./components/DownloadChapterControl";
export { DownloadsView } from "./components/DownloadsView";
export { ChapterCheckbox, SavedChapterMark } from "./components/SavedChapterMark";
export { ServiceWorkerBoundary } from "./components/ServiceWorkerBoundary";
export { useOfflineState, useSavedChapter, useStorageScope } from "./hooks";
export { buildSaveRequest, chapterCacheKey, isSavableChapter } from "./save-request";
export { resolveApiBase } from "./client";
export { buildNovelSaveRequest } from "./novel-save-request";
export { useChapterPicker, type ChapterPicker } from "./use-chapter-picker";
export type { ChapterDownloadState } from "./series-downloads";
export type { OfflineState, SavedChapterEntry, SavedChapterStatus } from "./types";
