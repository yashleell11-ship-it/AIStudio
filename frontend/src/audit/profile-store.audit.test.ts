/**
 * AUDIT (shard: profile-store). WS-2: hydration of `mm.active-profile` must be
 * total. Whatever the key holds, the store must reach `hasHydrated: true`; a
 * blob this store never wrote must read as "no profile" AND be cleared, so the
 * next load starts clean; storage that throws must not take the picker down.
 * Pure-module tests: the real store runs against an in-memory localStorage.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ACTIVE_PROFILE_STORAGE_KEY as KEY } from "@/features/profiles/storage-key";
import type { ActiveProfile } from "@/features/profiles/types";

class MemoryStorage {
  private readonly entries = new Map<string, string>();
  get length() { return this.entries.size; }
  key(i: number) { return [...this.entries.keys()][i] ?? null; }
  getItem(k: string) { return this.entries.get(k) ?? null; }
  setItem(k: string, v: string) { this.entries.set(k, String(v)); }
  removeItem(k: string) { this.entries.delete(k); }
  clear() { this.entries.clear(); }
}

const g = globalThis as unknown as Record<string, unknown>;

/** Boot the real store against `seed`: a raw blob, nothing, or a storage from a previous load. */
async function loadProfileStore(seed: string | null | MemoryStorage) {
  vi.resetModules();
  const storage = seed instanceof MemoryStorage ? seed : new MemoryStorage();
  if (typeof seed === "string") storage.setItem(KEY, seed);
  const removed = vi.spyOn(storage, "removeItem");
  removed.mockClear();
  g.window = { localStorage: storage };
  const mod = await import("@/features/profiles/store");
  return { store: mod.useActiveProfileStore, getActiveProfileId: mod.getActiveProfileId, storage, removed };
}

const VALID: ActiveProfile = { id: 7, name: "Y", avatar_key: "a", mood: "default" };
const envelope = (state: unknown, version: unknown = 0) => JSON.stringify({ state, version });

afterEach(() => {
  delete g.window;
  vi.restoreAllMocks();
});

describe("WS-2 blobs this store wrote hydrate as written", () => {
  it("a selection is restored and the key left alone", async () => {
    const { store, removed } = await loadProfileStore(envelope({ activeProfile: VALID }));
    expect(store.getState().hasHydrated).toBe(true);
    expect(store.getState().activeProfile).toEqual(VALID);
    expect(removed).not.toHaveBeenCalled();
  });

  it("a cleared selection (activeProfile: null) is a valid 'no profile', not corruption", async () => {
    const { store, removed } = await loadProfileStore(envelope({ activeProfile: null }));
    expect(store.getState().hasHydrated).toBe(true);
    expect(store.getState().activeProfile).toBeNull();
    expect(removed).not.toHaveBeenCalled();
  });

  it("nothing stored hydrates to 'no profile'", async () => {
    const { store, removed } = await loadProfileStore(null);
    expect(store.getState().hasHydrated).toBe(true);
    expect(store.getState().activeProfile).toBeNull();
    expect(removed).not.toHaveBeenCalled();
  });

  it("extra fields from a fuller profile are dropped; the selection is kept", async () => {
    const fuller = { ...VALID, sort_order: 1, mature_content_enabled: true, created_at: "2026-01-01" };
    const { store, removed } = await loadProfileStore(envelope({ activeProfile: fuller }));
    expect(store.getState().activeProfile).toEqual(VALID);
    expect(removed).not.toHaveBeenCalled();
  });

  it("an unknown mood value falls back to 'default' rather than dropping the selection", async () => {
    const { store, removed } = await loadProfileStore(envelope({ activeProfile: { ...VALID, mood: "vaporwave" } }));
    expect(store.getState().activeProfile).toEqual({ ...VALID, mood: "default" });
    expect(removed).not.toHaveBeenCalled();
  });

  it("a version this store has no migration for hydrates to 'no profile' without bricking", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { store } = await loadProfileStore(envelope({ activeProfile: VALID }, 1));
    expect(store.getState().hasHydrated).toBe(true);
    expect(store.getState().activeProfile).toBeNull();
  });
});

const CORRUPT: [label: string, raw: string][] = [
  ["an empty string", ""],
  ["the literal 'undefined'", "undefined"],
  ["the literal 'null'", "null"],
  ["a truncated write", "{not json"],
  ["a write cut off mid-envelope", envelope({ activeProfile: VALID }).slice(0, -12)],
  ["a JSON array", "[1,2,3]"],
  ["a JSON number", "42"],
  ["a JSON string", '"mm.active-profile"'],
  ["an envelope whose state is a string", envelope("oops")],
  ["an envelope whose state is an array", envelope([VALID])],
  ["an envelope with no activeProfile key", envelope({})],
  ["the snapshot without the state envelope", JSON.stringify({ activeProfile: VALID })],
  ["activeProfile as a number", envelope({ activeProfile: 7 })],
  ["activeProfile as a string", envelope({ activeProfile: "7" })],
  ["activeProfile as an array", envelope({ activeProfile: [VALID] })],
  ["a string where the id should be", envelope({ activeProfile: { ...VALID, id: "7" } })],
  ["a float where the id should be", envelope({ activeProfile: { ...VALID, id: 7.5 } })],
  ["a snapshot with only an id", envelope({ activeProfile: { id: 7 } })],
  ["a snapshot missing mood", envelope({ activeProfile: { id: 7, name: "Y", avatar_key: "a" } })],
  ["a snapshot missing avatar_key", envelope({ activeProfile: { id: 7, name: "Y", mood: "default" } })],
  ["a number where the name should be", envelope({ activeProfile: { ...VALID, name: 42 } })],
  ["a number where avatar_key should be", envelope({ activeProfile: { ...VALID, avatar_key: 3 } })],
  ["a number where mood should be", envelope({ activeProfile: { ...VALID, mood: 1 } })],
];

describe("WS-2 blobs this store never wrote hydrate as 'no profile' and are cleared", () => {
  it.each(CORRUPT)("%s", async (_label, raw) => {
    const first = await loadProfileStore(raw);
    expect(first.store.getState().hasHydrated).toBe(true);
    expect(first.store.getState().activeProfile).toBeNull();
    expect(first.getActiveProfileId()).toBeNull();
    expect(first.removed).toHaveBeenCalledWith(KEY);
    expect(first.storage.getItem(KEY)).not.toBe(raw);

    // The point of clearing: the next load finds nothing to repair.
    const second = await loadProfileStore(first.storage);
    expect(second.store.getState().hasHydrated).toBe(true);
    expect(second.store.getState().activeProfile).toBeNull();
    expect(second.removed).not.toHaveBeenCalled();
  });
});

describe("WS-2 storage that throws never blocks hydration or the picker", () => {
  it("localStorage that throws on access (storage disabled) hydrates to 'no profile'", async () => {
    vi.resetModules();
    g.window = {
      get localStorage() {
        throw new Error("SecurityError: The operation is insecure.");
      },
    };
    const mod = await import("@/features/profiles/store");
    expect(mod.useActiveProfileStore.getState().hasHydrated).toBe(true);
    expect(mod.useActiveProfileStore.getState().activeProfile).toBeNull();
    // A selection made anyway drives this session from memory.
    expect(() => mod.useActiveProfileStore.getState().setActiveProfile(VALID)).not.toThrow();
    expect(mod.getActiveProfileId()).toBe(7);
  });

  it("a getItem that throws hydrates to 'no profile'", async () => {
    const storage = new MemoryStorage();
    storage.getItem = () => {
      throw new Error("SecurityError");
    };
    const { store } = await loadProfileStore(storage);
    expect(store.getState().hasHydrated).toBe(true);
    expect(store.getState().activeProfile).toBeNull();
  });

  it("a hydration that throws past the storage guards still opens the gate", async () => {
    // The soft brick was never really about JSON: zustand hands the rehydrate
    // callback an UNDEFINED state whenever hydration rejects, and a gate that
    // only flips on the success path stays shut forever. Reach that path the
    // one way a test can — a storage swapped in behind the guards.
    const { store } = await loadProfileStore(null);
    store.persist.setOptions({
      storage: {
        getItem: () => {
          throw new Error("hydration blew up somewhere we did not foresee");
        },
        setItem: () => {},
        removeItem: () => {},
      },
    });
    store.setState({ hasHydrated: false });
    await store.persist.rehydrate();
    expect(store.getState().hasHydrated).toBe(true);
  });

  it("a quota failure on write keeps the in-memory selection and does not throw", async () => {
    const { store, storage, getActiveProfileId } = await loadProfileStore(null);
    storage.setItem = () => {
      throw new Error("QuotaExceededError");
    };
    expect(() => store.getState().setActiveProfile(VALID)).not.toThrow();
    expect(getActiveProfileId()).toBe(7);
    expect(() => store.getState().clearActiveProfile()).not.toThrow();
    expect(getActiveProfileId()).toBeNull();
  });
});
