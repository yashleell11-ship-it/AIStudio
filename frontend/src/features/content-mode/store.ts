import {
  activeStorageKey,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";
import { parseContentMode, type ContentMode } from "./mode";

/**
 * The active profile's content mode.
 *
 * Per (user, profile) via `@/lib/scoped-storage`, like the reading theme and
 * every other client-side preference: two personas on one browser have
 * different libraries, and one of them living in Novels mode must not decide
 * what the other sees when they pick up the tab.
 *
 * Stored as a bare string, so `useSyncExternalStore`'s reference comparison is
 * free and no snapshot cache is needed (unlike the object-shaped stores).
 */

const CONTENT_MODE_BASE = "mm.content-mode";

/** Same-tab notification; `storage` only fires in tabs that did not write. */
const CONTENT_MODE_EVENT = "mm:content-mode";

/** The stored choice for the active profile, or `null` when there is none. */
export function readStoredContentMode(): ContentMode | null {
  return parseContentMode(readScopedString(CONTENT_MODE_BASE));
}

export function writeContentMode(mode: ContentMode): void {
  if (typeof window === "undefined") return;
  writeScopedString(CONTENT_MODE_BASE, mode);
  window.dispatchEvent(new Event(CONTENT_MODE_EVENT));
}

export function getContentModeSnapshot(): ContentMode | null {
  return readStoredContentMode();
}

export function getContentModeServerSnapshot(): ContentMode | null {
  // No storage on the server, and the mode is per-profile, so there is nothing
  // to serialise. `null` renders the default (manga), which is also what the
  // flag-off deployment renders — no hydration mismatch either way.
  return null;
}

export function subscribeContentMode(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => onStoreChange();
  window.addEventListener(CONTENT_MODE_EVENT, handler);
  window.addEventListener("storage", handler);
  // A profile switch changes which key this reads without touching storage.
  const unsubscribeScope = subscribeStorageScope(handler);
  return () => {
    window.removeEventListener(CONTENT_MODE_EVENT, handler);
    window.removeEventListener("storage", handler);
    unsubscribeScope();
  };
}

/** Whether a choice is actually stored, as opposed to falling back. */
export function hasStoredContentMode(): boolean {
  return (
    activeStorageKey(CONTENT_MODE_BASE) !== null && readStoredContentMode() !== null
  );
}
