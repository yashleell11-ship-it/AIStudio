/**
 * AUDIT (shard: sw-bounds). What the service worker's caches are allowed to
 * cost the origin, and how the page keeps the worker told who is looking.
 *
 * Two findings, both about the one thing in this origin a reader would miss:
 *
 *   WS-3  the browser evicts under storage pressure per ORIGIN, and it takes
 *         the whole origin — saved chapters go with whatever pushed it over.
 *         So the per-profile API cache must be bounded, and the page must ask
 *         for persistent storage as soon as it knows there is something to
 *         protect, not only at the moment of the next save.
 *   WS-A2 a worker forgets every tab's scope when the browser stops it, and
 *         a new worker never knew them. The page has to re-introduce itself on
 *         `controllerchange` and when the tab is looked at again, or a restart
 *         leaves page images answered from the network — or, before the
 *         header check, from another profile's cache.
 *
 * The worker half runs the shipped `sw.js` in the in-memory harness; the page
 * half runs the shipped `client.ts` against a hand-rolled `window`, since the
 * suite has no DOM.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  API_BASE,
  CONTENT_VERSION,
  RUNTIME_VERSION,
  createHarness,
  readIndex,
  route,
  type Harness,
} from "@/features/offline/sw-harness.testing";
import type { OfflineWorkerState, SavedChapterEntry } from "@/features/offline/types";

const ALICE = { userId: 1, profileId: 7 };
const ALICE_API_CACHE = `mm-api-${RUNTIME_VERSION}-u1p7`;
const ALICE_SAVED_CACHE = `mm-offline-${CONTENT_VERSION}-u1p7`;

/** Mirrors MAX_API_ENTRIES in `public/sw.js`. */
const API_ENTRY_CAP = 200;

// ---------------------------------------------------------------------------
// WS-3, worker half: routine API traffic is bounded and never touches downloads.
// ---------------------------------------------------------------------------

const SOURCE = "asura";
const PAGE_ONE = `${API_BASE}/sources/${SOURCE}/pages/p1/image`;
const PAGE_TWO = `${API_BASE}/sources/${SOURCE}/pages/p2/image`;
const PAYLOAD = `${API_BASE}/reader/chapter/manifest?source=${SOURCE}&series=s&chapter=c`;
const KEY = `chapter:${SOURCE}:s:c`;

async function bootWorker(): Promise<Harness> {
  const h = createHarness();
  route(h, PAGE_ONE, { body: "page-one-bytes", headers: { "content-type": "image/jpeg" } });
  route(h, PAGE_TWO, { body: "page-two-bytes", headers: { "content-type": "image/jpeg" } });
  await h.dispatchInstall();
  await h.dispatchActivate();
  await h.dispatchMessage({ type: "mm-offline/set-scope", scope: ALICE, apiBase: API_BASE });
  return h;
}

/** Open `count` series chapter lists in a row — a season of ordinary browsing. */
async function browse(h: Harness, count: number): Promise<void> {
  for (let i = 0; i < count; i += 1) {
    const url = `${API_BASE}/library/series/${i}/chapters`;
    route(h, url, { body: `{"id":${i}}` });
    await h.dispatchFetch({ url });
  }
}

describe("WS-3 the per-profile API cache cannot grow the origin toward eviction", () => {
  it("holds at most the cap however many series are opened, newest kept", async () => {
    const h = await bootWorker();
    await browse(h, 3 * API_ENTRY_CAP);

    const cache = h.cacheFor(ALICE_API_CACHE)!;
    expect(cache.entries.size).toBeLessThanOrEqual(API_ENTRY_CAP);
    expect(await cache.match(`${API_BASE}/library/series/599/chapters`)).toBeTruthy();
    expect(await cache.match(`${API_BASE}/library/series/0/chapters`)).toBeUndefined();
  });

  it("leaves every saved page exactly where it was after that browsing", async () => {
    const h = await bootWorker();
    await h.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: {
        key: KEY,
        sourceId: SOURCE,
        seriesKey: "s",
        chapterKey: "c",
        title: "c",
        seriesTitle: "s",
        medium: "manga",
        scope: ALICE,
        profileId: ALICE.profileId,
        documentUrl: null,
        payloadUrl: PAYLOAD,
        payloadJson: '{"pages":[]}',
        imageUrls: [PAGE_ONE, PAGE_TWO],
        extraUrls: [],
      },
    });
    const before = [...h.cacheFor(ALICE_SAVED_CACHE)!.entries.keys()].sort();

    await browse(h, 3 * API_ENTRY_CAP);

    const saved = h.cacheFor(ALICE_SAVED_CACHE)!;
    expect([...saved.entries.keys()].sort()).toEqual(before);
    expect(await saved.match(PAGE_ONE)).toBeTruthy();
    expect(await saved.match(PAGE_TWO)).toBeTruthy();
    const index = await readIndex(h, ALICE_SAVED_CACHE);
    expect(index?.entries[KEY].status).toBe("ready");
  });
});

// ---------------------------------------------------------------------------
// WS-A2, worker half: a worker that has just started says so.
// ---------------------------------------------------------------------------

describe("WS-A2 a worker that has just started announces itself", () => {
  it("tells the tabs already open, which are the only ones that know their profile", async () => {
    // Evaluating `sw.js` again IS the restart: the browser stops an idle worker
    // after about thirty seconds and starts a fresh one whose `clientScopes` is
    // empty. No lifecycle event fires on the page for that, so unless the
    // worker speaks first nothing asks the tabs to introduce themselves again.
    const h = createHarness();
    await h.dispatchInstall();

    expect(h.clients[0].messages).toContainEqual({ type: "mm-offline/worker-started" });
  });
});

// ---------------------------------------------------------------------------
// The page half: `client.ts` against a hand-rolled window.
// ---------------------------------------------------------------------------

type Listener = (event: unknown) => void;

interface PageFixture {
  /** Every message the page posted to the active worker, in order. */
  posted: { type?: unknown; scope?: unknown }[];
  persistCalls: number;
  fireWorkerEvent(type: string): void;
  /** What the worker itself sends, as opposed to a reply this page asked for. */
  fireWorkerMessage(data: unknown): void;
  setVisibility(state: "visible" | "hidden"): void;
}

const g = globalThis as unknown as Record<string, unknown>;

function savedEntry(): SavedChapterEntry {
  return {
    key: KEY,
    sourceId: SOURCE,
    seriesKey: "s",
    chapterKey: "c",
    title: "c",
    seriesTitle: "s",
    medium: "manga",
    pageCount: 2,
    payloadUrl: PAYLOAD,
    urls: [PAGE_ONE, PAGE_TWO],
    savedPages: 2,
    bytes: 28,
    status: "ready",
    failed: 0,
    stale: false,
    savedAt: 1,
    lastOpenedAt: null,
    readAt: null,
  };
}

/**
 * A `window` with just enough service-worker surface for `client.ts`: a
 * registration whose active worker answers every message with `state`, and
 * event targets for the container and the document.
 */
function mountPage(options: { entries?: SavedChapterEntry[]; persisted?: boolean } = {}): PageFixture {
  const posted: PageFixture["posted"] = [];
  const containerListeners = new Map<string, Set<Listener>>();
  const documentListeners = new Map<string, Set<Listener>>();
  const state: OfflineWorkerState = {
    scopeToken: "u1p7",
    entries: options.entries ?? [],
    retentionMs: null,
    estimate: null,
    openChapterKey: null,
  };

  function target(map: Map<string, Set<Listener>>) {
    return {
      addEventListener(type: string, listener: Listener) {
        if (!map.has(type)) map.set(type, new Set());
        map.get(type)!.add(listener);
      },
      removeEventListener(type: string, listener: Listener) {
        map.get(type)?.delete(listener);
      },
    };
  }

  const active = {
    postMessage(message: PageFixture["posted"][number], transfer?: MessagePort[]) {
      posted.push(message);
      transfer?.[0]?.postMessage({ ok: true, state });
    },
  };
  const registration = { active, waiting: null, installing: null, addEventListener() {} };
  const container = {
    ...target(containerListeners),
    controller: active,
    ready: Promise.resolve(registration),
    register: async () => registration,
  };
  const fixture: PageFixture = {
    posted,
    persistCalls: 0,
    fireWorkerEvent(type) {
      for (const listener of containerListeners.get(type) ?? []) listener({ type });
    },
    fireWorkerMessage(data) {
      for (const listener of containerListeners.get("message") ?? []) {
        listener({ type: "message", data });
      }
    },
    setVisibility(visibilityState) {
      (g.document as { visibilityState: string }).visibilityState = visibilityState;
      for (const listener of documentListeners.get("visibilitychange") ?? []) {
        listener({ type: "visibilitychange" });
      }
    },
  };
  let persisted = options.persisted ?? false;

  g.document = { visibilityState: "visible", ...target(documentListeners) };
  g.window = {
    isSecureContext: true,
    location: { origin: "https://manhwa.example" },
    setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
    clearTimeout: (id: unknown) => clearTimeout(id as NodeJS.Timeout),
    navigator: {
      serviceWorker: container,
      storage: {
        persisted: async () => persisted,
        persist: async () => {
          fixture.persistCalls += 1;
          persisted = true;
          return true;
        },
      },
    },
  };
  return fixture;
}

async function loadClient() {
  vi.resetModules();
  return import("@/features/offline/client");
}

/** Wait for the message-port round trips the page makes to settle. */
async function settle(): Promise<void> {
  for (let i = 0; i < 4; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1));
  }
}

function scopeMessages(fixture: PageFixture) {
  return fixture.posted.filter((message) => message.type === "mm-offline/set-scope");
}

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_ENABLE_SW", "1");
});

afterEach(() => {
  vi.unstubAllEnvs();
  delete g.window;
  delete g.document;
});

describe("WS-3 the page asks for persistent storage as soon as there is something to keep", () => {
  it("requests it on load when the profile already has saved chapters", async () => {
    const page = mountPage({ entries: [savedEntry()] });
    const client = await loadClient();
    await client.registerOfflineWorker();
    await client.publishScope(ALICE);
    await settle();

    // Nothing was saved this session; the chapters were there when the page
    // opened, and that alone must be enough to ask.
    expect(page.persistCalls).toBe(1);
  });

  it("does not ask for an empty profile — Firefox prompts, and there is nothing to protect", async () => {
    const page = mountPage({ entries: [] });
    const client = await loadClient();
    await client.registerOfflineWorker();
    await client.publishScope(ALICE);
    await settle();

    expect(page.persistCalls).toBe(0);
  });

  it("does not ask again once the browser has already granted it", async () => {
    const page = mountPage({ entries: [savedEntry()], persisted: true });
    const client = await loadClient();
    await client.registerOfflineWorker();
    await client.publishScope(ALICE);
    await settle();

    expect(page.persistCalls).toBe(0);
  });
});

describe("WS-A2 the page re-introduces its profile to a worker that cannot know it", () => {
  it("re-publishes the scope on controllerchange", async () => {
    const page = mountPage();
    const client = await loadClient();
    await client.registerOfflineWorker();
    await client.publishScope(ALICE);
    expect(scopeMessages(page)).toHaveLength(1);

    // A new worker took over — a build another tab chose to activate, or a
    // page loaded before the worker existed being claimed. Either way it has
    // never heard from this tab.
    page.fireWorkerEvent("controllerchange");
    await settle();

    expect(scopeMessages(page)).toHaveLength(2);
    expect(scopeMessages(page)[1].scope).toEqual(ALICE);
  });

  it("re-publishes when the worker announces that it has just started", async () => {
    const page = mountPage();
    const client = await loadClient();
    await client.registerOfflineWorker();
    await client.publishScope(ALICE);

    // The restart the page has no other way to hear about: no lifecycle event
    // fires when the browser stops an idle worker and starts a fresh one.
    page.fireWorkerMessage({ type: "mm-offline/worker-started" });
    await settle();

    expect(scopeMessages(page)).toHaveLength(2);
    expect(scopeMessages(page)[1].scope).toEqual(ALICE);
  });

  it("still applies a state message, which the announcement branch sits in front of", async () => {
    const page = mountPage();
    const client = await loadClient();
    await client.registerOfflineWorker();
    await client.publishScope(ALICE);

    page.fireWorkerMessage({
      type: "mm-offline/state",
      state: {
        scopeToken: "u1p7",
        entries: [savedEntry()],
        retentionMs: null,
        estimate: null,
        openChapterKey: null,
      },
    });
    await settle();

    expect(client.getOfflineSnapshot().entries).toHaveLength(1);
  });

  it("re-publishes the scope when the tab is looked at again", async () => {
    const page = mountPage();
    const client = await loadClient();
    await client.registerOfflineWorker();
    await client.publishScope(ALICE);

    page.setVisibility("hidden");
    await settle();
    // Going to the background is not a reason to talk to the worker.
    expect(scopeMessages(page)).toHaveLength(1);

    page.setVisibility("visible");
    await settle();
    expect(scopeMessages(page)).toHaveLength(2);
    expect(scopeMessages(page)[1].scope).toEqual(ALICE);
  });

  it("re-publishes a cleared scope too, so a signed-out tab stays signed out", async () => {
    const page = mountPage();
    const client = await loadClient();
    await client.registerOfflineWorker();
    await client.publishScope(ALICE);
    await client.publishScope(null);

    page.fireWorkerEvent("controllerchange");
    await settle();

    const last = scopeMessages(page).at(-1);
    expect(last?.scope).toBeNull();
  });

  it("stays quiet before the tab has published anything", async () => {
    const page = mountPage();
    const client = await loadClient();
    await client.registerOfflineWorker();

    page.fireWorkerEvent("controllerchange");
    page.setVisibility("visible");
    await settle();

    // No scope yet means nothing to say — publishing null here would tell the
    // worker "nobody" for a tab whose profile is still resolving.
    expect(scopeMessages(page)).toHaveLength(0);
  });
});
