import {
  activeStorageKey,
  discardLegacyValue,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";

/**
 * The terms offered back as "Recent" chips under the search box.
 *
 * Per (user, profile): searched titles are as personal as the library they find,
 * and a device-global list showed one persona's terms to the next — including
 * adult ones inside a profile whose 18+ gate is off, where the gate hides the
 * series but the term naming it would sit on screen.
 *
 * Lives outside the view so the store is testable on its own and importable
 * (by the storage-scope boundary) without dragging the search UI along.
 */

const RECENT_SEARCHES_BASE = "manhwamaniacs:recent-searches";

/**
 * The key this list used before it was scoped. Scoped keys carry a
 * `::u<user>:p<profile>` suffix, so the bare base is only ever the pre-scoping
 * list. See {@link discardLegacyRecentSearches}.
 */
const LEGACY_RECENT_SEARCHES_KEY = RECENT_SEARCHES_BASE;

/** Same-tab notification; `storage` only fires in the tabs that did not write. */
const RECENT_SEARCHES_EVENT = "manhwamaniacs:recent-searches";

const MAX_RECENT_SEARCHES = 4;

/**
 * The shortest term worth REMEMBERING — not the shortest one worth searching.
 * The search box runs from the first character; a chip offering to search "a"
 * again is not a shortcut to anything, and four of them would be the whole list.
 */
const MIN_TERM_LENGTH = 2;

const EMPTY_SEARCHES: string[] = [];

export function parseRecentSearches(raw: string | null): string[] {
  if (!raw) {
    return EMPTY_SEARCHES;
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return EMPTY_SEARCHES;
    }
    return parsed
      .filter((item): item is string => typeof item === "string")
      .slice(0, MAX_RECENT_SEARCHES);
  } catch {
    return EMPTY_SEARCHES;
  }
}

/**
 * The list after searching `term`: most recent first, no case-insensitive
 * duplicate, capped. Terms too short to search are not remembered.
 */
export function nextRecentSearches(
  existing: readonly string[],
  term: string,
): string[] {
  const trimmed = term.trim();
  if (trimmed.length < MIN_TERM_LENGTH) {
    return [...existing];
  }
  const withoutDuplicate = existing.filter(
    (item) => item.toLowerCase() !== trimmed.toLowerCase(),
  );
  return [trimmed, ...withoutDuplicate].slice(0, MAX_RECENT_SEARCHES);
}

/** Empty with no active profile — there is no unscoped list to fall back to. */
export function readRecentSearches(): string[] {
  return parseRecentSearches(readScopedString(RECENT_SEARCHES_BASE));
}

export function writeRecentSearch(term: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const next = nextRecentSearches(readRecentSearches(), term);
  writeScopedString(RECENT_SEARCHES_BASE, JSON.stringify(next));
  window.dispatchEvent(new Event(RECENT_SEARCHES_EVENT));
}

// `useSyncExternalStore` compares snapshots by reference, so parsing on every
// read would re-render forever. Cache by scoped key + raw value: both the
// stored list and the profile it belongs to have to change to invalidate it.
let snapshot: { key: string | null; raw: string | null; value: string[] } = {
  key: null,
  raw: null,
  value: EMPTY_SEARCHES,
};

export function getRecentSearchesSnapshot(): string[] {
  const key = activeStorageKey(RECENT_SEARCHES_BASE);
  const raw = readScopedString(RECENT_SEARCHES_BASE);
  if (snapshot.key !== key || snapshot.raw !== raw) {
    snapshot = { key, raw, value: parseRecentSearches(raw) };
  }
  return snapshot.value;
}

export function getRecentSearchesServerSnapshot(): string[] {
  return EMPTY_SEARCHES;
}

export function subscribeRecentSearches(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }
  const handler = () => onStoreChange();
  window.addEventListener(RECENT_SEARCHES_EVENT, handler);
  window.addEventListener("storage", handler);
  // A profile switch changes which key this reads without touching storage,
  // so no DOM event announces it.
  const unsubscribeScope = subscribeStorageScope(handler);
  return () => {
    window.removeEventListener(RECENT_SEARCHES_EVENT, handler);
    window.removeEventListener("storage", handler);
    unsubscribeScope();
  };
}

/**
 * Drop the pre-scoping `manhwamaniacs:recent-searches` list without adopting it.
 *
 * Discarded, not adopted the way online reading progress is: this is four terms
 * of convenience that the next search regenerates, and it is also the store most
 * likely to name adult titles. Giving it to whichever profile happens to open
 * the app first could put in front of a restricted profile exactly what its 18+
 * gate exists to keep out. Losing four chips is the cheaper mistake.
 */
export function discardLegacyRecentSearches(): void {
  discardLegacyValue(LEGACY_RECENT_SEARCHES_KEY);
}
