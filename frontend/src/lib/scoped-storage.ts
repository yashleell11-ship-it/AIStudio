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

/**
 * Write `base` in the active scope. Drops the write when there is no scope.
 *
 * A full origin gets ONE recovery attempt: the store that overflows is rarely
 * the store that filled the quota — a reading preference dropped because a
 * year of chapter positions is in the way — so the capped families below give
 * up their oldest entries and the write is tried again. Still best-effort
 * after that, and still silent: there is nothing a preference write can
 * usefully say about someone else's storage.
 */
export function writeScopedString(base: string, value: string): void {
  if (setScoped(base, value) === "full" && relieveQuota()) {
    setScoped(base, value);
  }
}

/**
 * A family of keys sharing one prefix — one entry per chapter, series, or
 * whatever the caller indexes by — held to a fixed count per profile.
 *
 * Per-item keys are otherwise UNBOUNDED: a reader that opens ten thousand
 * chapters writes ten thousand keys and nothing ever removes one. That ends at
 * the origin quota, and it ends badly, because every write here is
 * fire-and-forget: the first failure is swallowed and so is every one after it,
 * so the reader stops remembering anything at all with no signal anywhere. A
 * cap plus least-recently-used eviction means the quota is never reached by
 * this data, and the entries given up are the ones nobody has opened in
 * months.
 */
export interface CappedKeyspace {
  /** Base-key prefix each entry carries; an entry's base is `prefix + id`. */
  prefix: string;
  /**
   * Base key holding the recency order. Deliberately NOT under `prefix`, so no
   * entry id can name it and the sweep below cannot mistake it for an entry.
   */
  orderKey: string;
  /** Entries retained per profile. */
  limit: number;
}

/**
 * Share of the family given up when a write meets a full origin. A quarter
 * frees room for the write many times over without throwing away a reading
 * history that took months to build.
 */
const QUOTA_RELIEF = 0.25;

const cappedFamilies = new Map<string, CappedKeyspace>();

/**
 * Declare a family, so any scoped write that meets a full origin has something
 * it is allowed to throw away. Keyed by `orderKey` so a module re-evaluated in
 * development registers the same family rather than a second copy of it.
 */
export function registerCappedKeyspace(space: CappedKeyspace): CappedKeyspace {
  cappedFamilies.set(space.orderKey, space);
  return space;
}

type WriteOutcome = "ok" | "full" | "refused";

/**
 * Quota is the failure this cap exists for and the only one worth evicting
 * over: a storage refusing every write (site data blocked, private mode) would
 * just lose more data to a pointless eviction pass. Firefox and older WebKit
 * name and number the same condition differently.
 */
function isQuotaExceeded(error: unknown): boolean {
  if (typeof error !== "object" || error === null) {
    return false;
  }
  const { name, code } = error as { name?: unknown; code?: unknown };
  return (
    name === "QuotaExceededError" ||
    name === "NS_ERROR_DOM_QUOTA_REACHED" ||
    code === 22 ||
    code === 1014
  );
}

function setScoped(base: string, value: string): WriteOutcome {
  const key = activeStorageKey(base);
  if (key === null || typeof window === "undefined") {
    return "refused";
  }
  try {
    window.localStorage.setItem(key, value);
    return "ok";
  } catch (error) {
    return isQuotaExceeded(error) ? "full" : "refused";
  }
}

function removeScoped(base: string): void {
  const key = activeStorageKey(base);
  if (key === null || typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Best-effort: the entry is being forgotten either way.
  }
}

/**
 * Entry ids already in storage, for a family with no order recorded yet.
 *
 * Every install that read a chapter before the cap existed carries hundreds of
 * these keys and no record of them. Without this sweep they would be invisible
 * to eviction and stay forever — exactly the growth the cap is here to stop.
 * Their true order is lost, so they are adopted behind whatever is being
 * written now; a wrong guess costs one chapter's remembered position.
 */
function sweepStoredEntries(space: CappedKeyspace): string[] {
  const suffix = activeStorageKey("");
  if (suffix === null || typeof window === "undefined") {
    return [];
  }
  const found: string[] = [];
  try {
    const store = window.localStorage;
    for (let index = 0; index < store.length; index += 1) {
      const key = store.key(index);
      if (key === null || !key.endsWith(suffix)) continue;
      const base = key.slice(0, key.length - suffix.length);
      if (base.startsWith(space.prefix)) {
        found.push(base.slice(space.prefix.length));
      }
    }
  } catch {
    return [];
  }
  return found;
}

/** Most-recently-used first. */
function readOrder(space: CappedKeyspace): string[] {
  const raw = readScopedString(space.orderKey);
  if (raw !== null) {
    try {
      const parsed: unknown = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.filter((id): id is string => typeof id === "string");
      }
    } catch {
      // Unreadable order: rebuild it from what is actually stored.
    }
  }
  return sweepStoredEntries(space);
}

function writeOrder(space: CappedKeyspace, order: readonly string[]): void {
  setScoped(space.orderKey, JSON.stringify(order));
}

/** Drop everything past `keep` from `order`, deleting each entry it names. */
function trim(space: CappedKeyspace, order: string[], keep: number): void {
  for (const id of order.splice(Math.max(1, keep))) {
    removeScoped(space.prefix + id);
  }
}

/** `order` with `id` at its head and the overflow evicted from storage. */
function retain(space: CappedKeyspace, order: string[], id: string): string[] {
  const next = [id, ...order.filter((other) => other !== id)];
  trim(space, next, space.limit);
  return next;
}

/**
 * An entry's value, counting the read as a use: without that the order would
 * be least-recently-WRITTEN, and a chapter re-opened daily but never scrolled
 * would age out from under the reader.
 */
export function readCappedEntry(space: CappedKeyspace, id: string): string | null {
  const value = readScopedString(space.prefix + id);
  if (value === null) {
    return null;
  }
  const order = readOrder(space);
  if (order[0] !== id || order.length > space.limit) {
    writeOrder(space, retain(space, order, id));
  }
  return value;
}

/**
 * Give up the oldest slice of every declared family. Reports whether anything
 * actually went, so a caller does not retry a write into a storage that had
 * nothing to give.
 */
function relieveQuota(): boolean {
  let freed = false;
  for (const space of cappedFamilies.values()) {
    const order = readOrder(space);
    const before = order.length;
    trim(space, order, Math.ceil(before * (1 - QUOTA_RELIEF)));
    if (order.length < before) {
      writeOrder(space, order);
      freed = true;
    }
  }
  return freed;
}

/** Write an entry, evicting to stay inside the cap and the origin's quota. */
export function writeCappedEntry(
  space: CappedKeyspace,
  id: string,
  value: string,
): void {
  let order = retain(space, readOrder(space), id);
  if (setScoped(space.prefix + id, value) === "full") {
    // Inside its own cap and still refused: the space is held by some other
    // store on the same origin, so relief has to come from all of them, this
    // family included. One retry — a second failure is nobody's to fix from
    // here, and the entry is stale rather than lost.
    writeOrder(space, order);
    if (relieveQuota()) {
      order = retain(space, readOrder(space), id);
      setScoped(space.prefix + id, value);
    }
  }
  writeOrder(space, order);
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
