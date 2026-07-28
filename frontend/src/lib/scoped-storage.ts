/**
 * localStorage scoped to the active (user, profile).
 *
 * Reading profiles are isolated server-side by `(user_id, profile_id)` — own
 * library, follows, reading progress and 18+ gate. Anything the client keeps in
 * localStorage holds the same kind of data, so it has to be scoped the same
 * way: a device-global key is read straight back by whoever picks up the
 * browser next, which on a shared device hands one persona another's reading
 * place or search history and quietly undoes the isolation.
 *
 * Keys are NAMESPACED rather than cleared on switch. Clearing would delete each
 * profile's own data every time the tab changes hands, so coming back to a
 * profile would find it blank — a different bug, not a fix.
 *
 * `reading_profiles.id` is a global autoincrement, so a profile id already
 * belongs to exactly one account and the user id is not needed to disambiguate.
 * It is in the key anyway so the key says whose data it is on inspection, and
 * so nothing silently merges if ids ever become per-account.
 */

export interface StorageScope {
  userId: number;
  profileId: number;
}

let activeScope: StorageScope | null = null;
const listeners = new Set<() => void>();

function sameScope(a: StorageScope | null, b: StorageScope | null): boolean {
  if (a === null || b === null) {
    return a === b;
  }
  return a.userId === b.userId && a.profileId === b.profileId;
}

/**
 * The namespaced key `base` is stored under for `scope`, or `null` when there
 * is no scope — no active profile means the data has no owner, and there is
 * deliberately no unscoped fallback to read instead.
 */
export function scopedStorageKey(
  base: string,
  scope: StorageScope | null,
): string | null {
  if (scope === null) {
    return null;
  }
  return `${base}::u${scope.userId}:p${scope.profileId}`;
}

export function getStorageScope(): StorageScope | null {
  return activeScope;
}

/**
 * Publish the scope every scoped store reads and writes under. Owned by the
 * provider that watches the session and the active profile; a no-op when the
 * scope is unchanged, so it can be called on every render pass.
 */
export function setStorageScope(next: StorageScope | null): void {
  if (sameScope(activeScope, next)) {
    return;
  }
  activeScope = next;
  for (const listener of listeners) {
    listener();
  }
}

/**
 * Subscribe to scope changes. Stores backing a `useSyncExternalStore` must
 * listen to this next to the `storage` event: on a profile switch the key under
 * the component's feet changes while localStorage itself does not, so nothing
 * else would tell it to re-read.
 */
export function subscribeStorageScope(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The active scope's key for `base`, or `null` when no profile is active. */
export function activeStorageKey(base: string): string | null {
  return scopedStorageKey(base, activeScope);
}

/** Raw value for `base` in the active scope. `null` when unscoped or unset. */
export function readScopedString(base: string): string | null {
  const key = activeStorageKey(base);
  if (key === null || typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** Write `base` in the active scope. Drops the write when there is no scope. */
export function writeScopedString(base: string, value: string): void {
  const key = activeStorageKey(base);
  if (key === null || typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore quota failures — every scoped store here is best-effort.
  }
}

/**
 * Take a value written before keys were scoped, for the active scope, exactly
 * once: the raw value is returned and the unscoped key removed in the same
 * step, so the next profile to ask finds nothing and cannot inherit it.
 *
 * Returns `null` and leaves the key untouched when no profile is active — an
 * unowned blob is never destroyed on the way past, it waits for a claimant.
 */
export function claimLegacyValue(legacyKey: string): string | null {
  if (activeScope === null || typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(legacyKey);
    if (raw === null) {
      return null;
    }
    window.localStorage.removeItem(legacyKey);
    return raw;
  } catch {
    return null;
  }
}

/**
 * Delete a pre-scoping key without reading it, for data whose owner cannot be
 * guessed safely and which is cheap to lose. Unlike {@link claimLegacyValue}
 * this needs no scope: the value is going regardless of who is looking.
 */
export function discardLegacyValue(legacyKey: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(legacyKey);
  } catch {
    // Nothing to recover from: the key is being dropped either way.
  }
}
