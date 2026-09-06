/**
 * AUDIT (shard: web-storage). Each test here asserts the behaviour a careful
 * operator would expect; a FAILING test is the proof of a finding, not a
 * broken suite. Pure-module tests only: the real store / worker sources are
 * executed against in-memory stand-ins, nothing renders.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  API_BASE,
  createHarness,
  route,
  type Harness,
} from "@/features/offline/sw-harness.testing";

// ---------------------------------------------------------------------------
// F1: a corrupted `mm.active-profile` blob leaves the profile gate un-hydrated
// forever (zustand persist reports the parse error to onRehydrateStorage with
// state=undefined, and store.ts only flips hasHydrated on the success path).
// ---------------------------------------------------------------------------

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

async function loadProfileStore(raw: string | null) {
  vi.resetModules();
  const storage = new MemoryStorage();
  if (raw !== null) storage.setItem("mm.active-profile", raw);
  // zustand's default persist storage is `createJSONStorage(() => window.localStorage)`.
  g.window = { localStorage: storage };
  g.localStorage = storage;
  const mod = await import("@/features/profiles/store");
  return { store: mod.useActiveProfileStore, storage };
}

describe("F1 active-profile persistence survives a corrupted localStorage value", () => {
  afterEach(() => {
    delete g.localStorage;
    delete g.window;
  });

  it("control: a valid blob hydrates and restores the selection", async () => {
    const { store } = await loadProfileStore(
      JSON.stringify({ state: { activeProfile: { id: 7, name: "Y", avatar_key: "a", mood: "default" } }, version: 0 }),
    );
    expect(store.getState().hasHydrated).toBe(true);
    expect(store.getState().activeProfile?.id).toBe(7);
  });

  it("control: no blob at all hydrates to 'no profile'", async () => {
    const { store } = await loadProfileStore(null);
    expect(store.getState().hasHydrated).toBe(true);
    expect(store.getState().activeProfile).toBeNull();
  });

  it("a corrupted blob must still finish hydration (as 'no profile') so the picker gate can run", async () => {
    const { store } = await loadProfileStore("{not json");
    // Expected: treated exactly like "nothing stored".
    expect(store.getState().activeProfile).toBeNull();
    expect(store.getState().hasHydrated).toBe(true);
  });

  it("a blob whose `state` is not an object must still finish hydration", async () => {
    const { store } = await loadProfileStore("null");
    expect(store.getState().hasHydrated).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// F2: after the worker is terminated and restarted (routine: Chrome kills an
// idle worker after ~30 s), `clientScopes` is empty and EVERY tab falls back
// to `persistedState` = whichever tab published last. Nothing on the page
// re-publishes after a restart (ServiceWorkerBoundary publishes on mount and
// on scope change only), so with two tabs on two profiles one tab is answered
// from — and writes into — the other profile's API cache.
// ---------------------------------------------------------------------------

const A = { userId: 1, profileId: 1 };
const B = { userId: 1, profileId: 2 };

async function publish(h: Harness, scope: typeof A | null, clientId: string) {
  await h.dispatchMessage({ type: "mm-offline/set-scope", scope, apiBase: API_BASE }, clientId);
}

/** A fresh worker instance over the SAME Cache Storage: what a restart is. */
function restart(previous: Harness): Harness {
  const next = createHarness();
  next.clients = previous.clients;
  for (const [name, cache] of previous.storage.caches) {
    next.storage.caches.set(name, cache);
  }
  return next;
}

describe("F2 worker restart with two tabs on two profiles", () => {
  let h1: Harness;
  const url = `${API_BASE}/library/series`;

  beforeEach(async () => {
    h1 = createHarness();
    h1.clients = [
      { id: "tab-a", messages: [] },
      { id: "tab-b", messages: [] },
    ];
    await h1.dispatchInstall();
    await h1.dispatchActivate();
    await publish(h1, A, "tab-a");
    route(h1, url, { body: '{"who":"A","adult":true}' });
    await h1.dispatchFetch({ url, clientId: "tab-a" });
    await publish(h1, B, "tab-b"); // B owns persistedState now
    route(h1, url, { body: '{"who":"B"}' });
    await h1.dispatchFetch({ url, clientId: "tab-b" });
  });

  it("tab A keeps being answered from profile A's cache after a restart", async () => {
    const h2 = restart(h1);
    route(h2, url, { body: '{"who":"A-fresh"}' });
    const outcome = await h2.dispatchFetch({ url, clientId: "tab-a" });
    const body = await outcome.response!.text();
    expect(body).not.toContain('"who":"B"');
  });

  it("tab A's fresh response never lands in profile B's API cache after a restart", async () => {
    const h2 = restart(h1);
    route(h2, url, { body: '{"who":"A-fresh","adult":true}' });
    await h2.dispatchFetch({ url, clientId: "tab-a" });
    const bCache = h2.cacheFor(`mm-api-v3-u${B.userId}p${B.profileId}`)!;
    const stored = bCache.entries.get(url);
    expect(stored?.body ?? "").not.toContain("A-fresh");
  });

  it("consequence: tab B is then served profile A's listing stale-first", async () => {
    const h2 = restart(h1);
    route(h2, url, { body: '{"who":"A-fresh","adult":true}' });
    await h2.dispatchFetch({ url, clientId: "tab-a" });
    h2.offline = true;
    const outcome = await h2.dispatchFetch({ url, clientId: "tab-b" });
    const body = outcome.response ? await outcome.response.text().catch(() => "") : "";
    expect(body).not.toContain("A-fresh");
  });
});

// ---------------------------------------------------------------------------
// F3: the per-profile API cache has no entry cap and no age-out. Every series
// detail / chapter list ever opened is one entry forever; only the document
// (60) and static (240) caches are trimmed.
// ---------------------------------------------------------------------------

describe("F3 per-profile API cache is bounded", () => {
  it("holds at most a few hundred entries however many series are opened", async () => {
    const h = createHarness();
    h.clients = [{ id: "tab-a", messages: [] }];
    await h.dispatchInstall();
    await h.dispatchActivate();
    await publish(h, A, "tab-a");
    const N = 600;
    for (let i = 0; i < N; i += 1) {
      const u = `${API_BASE}/library/series/${i}/chapters`;
      route(h, u, { body: `{"id":${i}}` });
      await h.dispatchFetch({ url: u, clientId: "tab-a" });
    }
    const cache = h.cacheFor(`mm-api-v3-u1p1`)!;
    expect(cache.entries.size).toBeLessThanOrEqual(300);
  });
});

// ---------------------------------------------------------------------------
// F4: per-chapter localStorage keys (scroll position, page ratios) are written
// for every chapter ever opened and never pruned; every scoped write swallows
// QuotaExceededError silently (scoped-storage.ts:107-111), so once the ~5 MB
// origin quota is reached the NEXT preference/progress write is dropped with
// no signal. This measures the growth through the real modules.
// ---------------------------------------------------------------------------

describe("F4 per-chapter localStorage keys are bounded", () => {
  it("keeps a bounded number of scroll/ratio keys per profile, and reports the size", async () => {
    vi.resetModules();
    const storage = new MemoryStorage();
    g.window = { localStorage: storage, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => true };
    const scoped = await import("@/lib/scoped-storage");
    const scroll = await import("@/features/reader/scroll-storage");
    const ratios = await import("@/features/reader/page-ratios");
    scoped.setStorageScope({ userId: 1, profileId: 1 });

    const CHAPTERS = 5000;
    // A realistic 40-page webtoon chapter: tall pages, two-decimal ratios.
    const shapes = Array.from({ length: 40 }, (_, i) => 1.4 + (i % 7) * 2.13);
    for (let i = 0; i < CHAPTERS; i += 1) {
      const key = `mangadex:some-series-slug-${i % 40}:chapter-${i}`;
      scroll.writeReaderPosition(key, { page: 12, offset: 340 });
      ratios.writePageRatios(key, shapes);
    }
    let chars = 0;
    for (let i = 0; i < storage.length; i += 1) {
      const k = storage.key(i)!;
      chars += k.length + (storage.getItem(k) ?? "").length;
    }
    // localStorage stores UTF-16: Chrome's ~5 MB cap is ~2.6M chars.
    console.log(`F4: ${storage.length} keys, ${chars} chars (~${(chars * 2 / 1024 / 1024).toFixed(2)} MB UTF-16) for ${CHAPTERS} chapters`);
    expect(storage.length).toBeLessThanOrEqual(2000);
    delete g.window;
  });
});
