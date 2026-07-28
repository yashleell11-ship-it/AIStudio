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

export { OfflineChapterControl } from "./components/OfflineChapterControl";
export { OfflineLibraryView } from "./components/OfflineLibraryView";
export { ServiceWorkerBoundary } from "./components/ServiceWorkerBoundary";
export { useOfflineState, useSavedChapter, useStorageScope } from "./hooks";
export { chapterCacheKey, isSavableChapter } from "./save-request";
export type { OfflineState, SavedChapterEntry, SavedChapterStatus } from "./types";
