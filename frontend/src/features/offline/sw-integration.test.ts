import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  API_BASE,
  ORIGIN,
  createHarness,
  readIndex,
  route,
  type Harness,
} from "./sw-harness.testing";
import { buildNovelSaveRequest } from "./novel-save-request";

/**
 * The service worker, executed.
 *
 * `policy-contract.test.ts` proves the worker decides correctly; this proves it
 * then does what it decided — which cache the bytes land in, what comes back
 * with the network down, and what a profile switch can and cannot see. Those
 * are the failures that would only otherwise be found on a train.
 *
 * URLs are source-native (spec §3.2): the chapter payload is
 * `/reader/chapter/manifest?source=&series=&chapter=` and a page is
 * `/sources/{source}/pages/{page}/image`.
 */

const ALICE = { userId: 1, profileId: 10 };
const BOB = { userId: 1, profileId: 11 };
const ALICE_CACHE = "mm-offline-c2-u1p10";
const BOB_CACHE = "mm-offline-c2-u1p11";

const SOURCE = "asura";
const SERIES = "series/solo-levelling";
const CHAPTER = "ch/50";
const KEY = `chapter:${SOURCE}:${SERIES}:${CHAPTER}`;

const PAGE_ONE = `${API_BASE}/sources/${SOURCE}/pages/p1/image`;
const PAGE_TWO = `${API_BASE}/sources/${SOURCE}/pages/p2/image`;
const PAYLOAD =
  `${API_BASE}/reader/chapter/manifest` +
  `?source=${SOURCE}&series=${encodeURIComponent(SERIES)}&chapter=${encodeURIComponent(CHAPTER)}`;
const DOCUMENT_URL = `${ORIGIN}/reader/${SOURCE}/${encodeURIComponent(SERIES)}/ch/50`;
const BOOKMARKS = `${API_BASE}/reader/bookmarks`;
const ALICE_API_CACHE = "mm-api-v2-u1p10";

const CHAPTER_BODY = JSON.stringify({
  source_id: SOURCE,
  series_key: SERIES,
  chapter_key: CHAPTER,
  chapter_number: 50,
  page_count: 2,
  pages: [
    { number: 1, url: PAGE_ONE },
    { number: 2, url: PAGE_TWO },
  ],
  prev: "ch/49",
  next: "ch/51",
});

function savePayload(scope: { userId: number; profileId: number }) {
  return {
    key: KEY,
    sourceId: SOURCE,
    seriesKey: SERIES,
    chapterKey: CHAPTER,
    title: "Chapter 50",
    seriesTitle: "Solo Levelling",
    medium: "manga",
    scope,
    profileId: scope.profileId,
    documentUrl: DOCUMENT_URL,
    payloadUrl: PAYLOAD,
    payloadJson: CHAPTER_BODY,
    imageUrls: [PAGE_ONE, PAGE_TWO],
    extraUrls: [PAYLOAD],
  };
}

let harness: Harness;

async function boot(scope = ALICE, clientId = "client-a"): Promise<void> {
  await harness.dispatchInstall();
  await harness.dispatchActivate();
  await harness.dispatchMessage(
    { type: "mm-offline/set-scope", scope, apiBase: API_BASE },
    clientId,
  );
}

beforeEach(() => {
  harness = createHarness();
  harness.clients.push({ id: "client-b", messages: [] });
  route(harness, "/offline-fallback.html", { body: "<h1>offline</h1>" });
  route(harness, "/icons/icon-192.png", { body: "icon" });
  route(harness, "/icons/icon-512.png", { body: "icon" });
  route(harness, "/manifest.webmanifest", { body: "{}" });
  route(harness, "/library", { body: "<html>library</html>" });
  route(harness, "/downloads", { body: "<html>downloads</html>" });
  route(harness, PAGE_ONE, { body: "page-one-bytes", headers: { "content-type": "image/jpeg" } });
  route(harness, PAGE_TWO, { body: "page-two-bytes", headers: { "content-type": "image/jpeg" } });
  route(harness, PAYLOAD, { body: CHAPTER_BODY });
  route(harness, DOCUMENT_URL, { body: "<html>reader</html>" });
  route(harness, BOOKMARKS, { body: '[{"id":1,"anchor_index":7}]' });
});

describe("install and activate", () => {
  it("precaches the offline fallback so there is always something to render", async () => {
    await harness.dispatchInstall();
    const shell = harness.cacheFor("mm-shell-v2");
    expect(await shell?.match("/offline-fallback.html")).toBeTruthy();
  });

  it("warms the installed app's start_url", async () => {
    await harness.dispatchInstall();
    await harness.dispatchActivate();
    const pages = harness.cacheFor("mm-pages-v2");
    expect(await pages?.match("/library")).toBeTruthy();
  });

  it("warms /downloads, the one page the offline fallback links to", async () => {
    await harness.dispatchInstall();
    await harness.dispatchActivate();
    const pages = harness.cacheFor("mm-pages-v2");
    expect(await pages?.match("/downloads")).toBeTruthy();
  });

  it("drops a superseded generation but never another profile's downloads", async () => {
    await harness.storage.open("mm-shell-v1");
    await harness.storage.open("mm-offline-c1-u1p10");
    await harness.storage.open(BOB_CACHE);
    await harness.storage.open("some-other-app");
    await harness.dispatchInstall();
    await harness.dispatchActivate();

    const names = await harness.cacheNames();
    expect(names).not.toContain("mm-shell-v1");
    // The old content generation is orphaned by the source-native migration.
    expect(names).not.toContain("mm-offline-c1-u1p10");
    expect(names).toContain(BOB_CACHE);
    expect(names).toContain("some-other-app");
  });
});

describe("saving a chapter", () => {
  it("stores every page under the saving profile's own cache", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    const cache = harness.cacheFor(ALICE_CACHE);
    expect(await cache?.match(PAGE_ONE)).toBeTruthy();
    expect(await cache?.match(PAGE_TWO)).toBeTruthy();
    expect(await cache?.match(PAYLOAD)).toBeTruthy();
    expect(await cache?.match(DOCUMENT_URL)).toBeTruthy();

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY].status).toBe("ready");
    expect(index?.entries[KEY].savedPages).toBe(2);
    expect(index?.entries[KEY].bytes).toBeGreaterThan(0);
    expect(index?.entries[KEY].medium).toBe("manga");
  });

  it("uses the payload the page already had instead of asking again", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    expect(harness.fetched.filter((url) => url === PAYLOAD)).toHaveLength(0);
  });

  it("resumes without re-downloading what is already stored", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    const firstPass = harness.fetched.filter((url) => url === PAGE_ONE).length;

    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    expect(harness.fetched.filter((url) => url === PAGE_ONE).length).toBe(firstPass);
  });

  it("reports holes rather than claiming a chapter is saved", async () => {
    harness.routes.delete(PAGE_TWO);
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY].status).toBe("partial");
    expect(index?.entries[KEY].savedPages).toBe(1);
    expect(index?.entries[KEY].failed).toBe(1);
  });

  it("refuses to save with no profile, rather than picking one", async () => {
    await boot();
    const reply = await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: { ...savePayload(ALICE), scope: null },
    });
    expect(reply.ok).toBe(false);
    expect(reply.reason).toBe("no-scope");
  });

  it("pauses instead of deleting unread chapters when the device is full", async () => {
    await boot();
    // No headroom at all, and nothing finished that could be evicted.
    harness.estimate = { usage: 9_999_000_000, quota: 10_000_000_000 };
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY].status).toBe("paused");
  });
});

describe("reading with no network", () => {
  it("serves a saved page image from the device", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({ url: PAGE_ONE, destination: "image" });
    expect(outcome.handled).toBe(true);
    expect(await outcome.response?.text()).toBe("page-one-bytes");
  });

  it("serves the saved chapter manifest so the reader can render at all", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({ url: PAYLOAD });
    expect(await outcome.response?.text()).toBe(CHAPTER_BODY);
  });

  it("falls back to a cached document, then to the offline page", async () => {
    await boot();
    await harness.dispatchFetch({ url: `${ORIGIN}/library`, mode: "navigate" });

    harness.offline = true;
    const cached = await harness.dispatchFetch({ url: `${ORIGIN}/library`, mode: "navigate" });
    expect(await cached.response?.text()).toBe("<html>library</html>");

    const unvisited = await harness.dispatchFetch({
      url: `${ORIGIN}/library/statistics`,
      mode: "navigate",
    });
    expect(await unvisited.response?.text()).toBe("<h1>offline</h1>");
  });

  it("opens a saved chapter's document that was never visited as a document", async () => {
    // The realistic path to a saved chapter: the user clicked through to the
    // reader inside the SPA, so the browser NEVER issued a navigation for the
    // reader route and the document cache has no copy of it. Saving fetches the
    // document on purpose for exactly this case; a cold offline launch (or a
    // reload on the train) must get it back rather than the offline page.
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: DOCUMENT_URL,
      mode: "navigate",
    });
    expect(await outcome.response?.text()).toBe("<html>reader</html>");
  });

  it("does not serve a saved document to a profile that did not save it", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchMessage(
      { type: "mm-offline/set-scope", scope: BOB, apiBase: API_BASE },
      "client-b",
    );

    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: DOCUMENT_URL,
      mode: "navigate",
      clientId: "client-b",
    });
    expect(await outcome.response?.text()).toBe("<h1>offline</h1>");
  });

  it("does not let the document cache grow without bound", async () => {
    await boot();
    for (let index = 0; index < 70; index += 1) {
      const url = `${ORIGIN}/library/${index}`;
      route(harness, url, { body: `series ${index}` });
      await harness.dispatchFetch({ url, mode: "navigate" });
    }
    const pages = harness.cacheFor("mm-pages-v2");
    expect((await (pages as { keys(): Promise<unknown[]> }).keys()).length).toBeLessThanOrEqual(
      60,
    );
    // The most recent visits survive; the oldest are the ones dropped.
    expect(await pages?.match(`${ORIGIN}/library/69`)).toBeTruthy();
    expect(await pages?.match(`${ORIGIN}/library/0`)).toBeUndefined();
  });

  it("ignores the query string when matching a cached reader document", async () => {
    await boot();
    await harness.dispatchFetch({ url: DOCUMENT_URL, mode: "navigate" });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: `${DOCUMENT_URL}?page=12`,
      mode: "navigate",
    });
    expect(await outcome.response?.text()).toBe("<html>reader</html>");
  });
});

describe("bookmarks with no network", () => {
  it("hands back the last listing it saw", async () => {
    await boot();
    await harness.dispatchFetch({ url: BOOKMARKS });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({ url: BOOKMARKS });
    expect(outcome.handled).toBe(true);
    expect(await outcome.response?.text()).toBe('[{"id":1,"anchor_index":7}]');
  });

  it("prefers the live listing whenever there is one", async () => {
    await boot();
    await harness.dispatchFetch({ url: BOOKMARKS });

    // A bookmark added since. A stale-first strategy would not show it.
    route(harness, BOOKMARKS, { body: '[{"id":2},{"id":1,"anchor_index":7}]' });
    const outcome = await harness.dispatchFetch({ url: BOOKMARKS });
    expect(await outcome.response?.text()).toBe('[{"id":2},{"id":1,"anchor_index":7}]');
  });

  it("fails honestly when it has never seen the listing", async () => {
    await boot();
    harness.offline = true;

    const outcome = await harness.dispatchFetch({ url: BOOKMARKS });
    // The screen shows its offline state rather than an empty bookmark list,
    // which would read as "you have no bookmarks".
    expect(outcome.response?.type ?? "error").toBe("error");
  });

  it("keeps one profile's saved places out of another's", async () => {
    await boot();
    await harness.dispatchFetch({ url: BOOKMARKS });
    expect(await harness.cacheNames()).toContain(ALICE_API_CACHE);

    await harness.dispatchMessage(
      { type: "mm-offline/set-scope", scope: BOB, apiBase: API_BASE },
      "client-a",
    );
    harness.offline = true;

    const outcome = await harness.dispatchFetch({ url: BOOKMARKS });
    expect(outcome.response?.type ?? "error").toBe("error");
  });
});

describe("profile isolation", () => {
  it("does not show one profile's saved chapters to another", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    const asBob = await harness.dispatchMessage(
      { type: "mm-offline/set-scope", scope: BOB, apiBase: API_BASE },
      "client-b",
    );
    expect((asBob.state as { entries: unknown[] }).entries).toHaveLength(0);
  });

  it("does not serve one profile's saved pages to another's tab", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchMessage(
      { type: "mm-offline/set-scope", scope: BOB, apiBase: API_BASE },
      "client-b",
    );

    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: PAGE_ONE,
      destination: "image",
      clientId: "client-b",
    });
    // Bob's tab gets a network failure, exactly as if the page had never been
    // saved — not Alice's bytes.
    expect(outcome.response).toBeNull();
    expect(outcome.error).toBeTruthy();
  });

  it("keeps serving the right tab after another tab switches profile", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchMessage(
      { type: "mm-offline/set-scope", scope: BOB, apiBase: API_BASE },
      "client-b",
    );

    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: PAGE_ONE,
      destination: "image",
      clientId: "client-a",
    });
    expect(await outcome.response?.text()).toBe("page-one-bytes");
  });

  it("stops serving saved content once the profile is cleared", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchMessage({
      type: "mm-offline/set-scope",
      scope: null,
      apiBase: API_BASE,
    });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({ url: PAGE_ONE, destination: "image" });
    expect(outcome.response).toBeNull();
  });
});

describe("what is never cached", () => {
  it("does not touch auth, online or offline", async () => {
    await boot();
    const outcome = await harness.dispatchFetch({ url: `${API_BASE}/auth/me` });
    expect(outcome.handled).toBe(false);
    const names = await harness.cacheNames();
    for (const name of names) {
      const cache = harness.cacheFor(name);
      expect(await cache?.match(`${API_BASE}/auth/me`)).toBeUndefined();
    }
  });

  it("does not touch a mutation", async () => {
    await boot();
    for (const method of ["POST", "PATCH", "DELETE"]) {
      const outcome = await harness.dispatchFetch({
        url: `${API_BASE}/reader/progress`,
        method,
      });
      expect(outcome.handled).toBe(false);
    }
  });

  it("does not answer a ranged request from a cache it cannot fill", async () => {
    await boot();
    const outcome = await harness.dispatchFetch({
      url: PAGE_ONE,
      destination: "image",
      headers: { range: "bytes=0-100" },
    });
    expect(outcome.handled).toBe(false);
  });
});

describe("stale-while-revalidate", () => {
  it("answers from cache and refreshes behind it, per profile", async () => {
    const listUrl = `${API_BASE}/library/series?limit=20`;
    route(harness, listUrl, { body: '["first"]' });
    await boot();

    const first = await harness.dispatchFetch({ url: listUrl });
    expect(await first.response?.text()).toBe('["first"]');

    route(harness, listUrl, { body: '["second"]' });
    const second = await harness.dispatchFetch({ url: listUrl });
    // The cached copy answers now; the refreshed one lands behind it.
    expect(await second.response?.text()).toBe('["first"]');

    const third = await harness.dispatchFetch({ url: listUrl });
    expect(await third.response?.text()).toBe('["second"]');
    expect(await harness.cacheNames()).toContain("mm-api-v2-u1p10");
  });

  it("caches nothing per-profile when there is no profile", async () => {
    await harness.dispatchInstall();
    await harness.dispatchActivate();
    await harness.dispatchMessage({
      type: "mm-offline/set-scope",
      scope: null,
      apiBase: API_BASE,
    });
    const listUrl = `${API_BASE}/library/series`;
    route(harness, listUrl, { body: "[]" });

    await harness.dispatchFetch({ url: listUrl });
    const names = await harness.cacheNames();
    expect(names.filter((name) => name.startsWith("mm-api-"))).toEqual([]);
  });
});

describe("retention and eviction", () => {
  // A fixed clock: the retention rule is `now - readAt >= retentionMs`, and with
  // a real wall clock the millisecond between stamping `readAt` and running the
  // sweep is not guaranteed to have elapsed — which is the timing race that made
  // this suite flaky. Faking `Date` makes every step's "now" explicit.
  const START = 1_700_000_000_000;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(START);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  async function saveAndFinish(): Promise<void> {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchMessage({
      type: "mm-offline/mark-finished",
      scope: ALICE,
      key: KEY,
    });
  }

  it("stamps a finish time and clears it when the chapter is reopened", async () => {
    await saveAndFinish();
    let index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY].readAt).toBe(START);

    vi.setSystemTime(START + 60_000);
    await harness.dispatchMessage({
      type: "mm-offline/mark-opened",
      scope: ALICE,
      key: KEY,
    });
    index = await readIndex(harness, ALICE_CACHE);
    // Re-reading cancels the deletion instead of it vanishing mid-scroll.
    expect(index?.entries[KEY].readAt).toBeNull();
  });

  it("deletes a finished chapter's pages once its retention has passed", async () => {
    await saveAndFinish();
    // Retention of one minute; the sweep runs an hour later, so it is due.
    await harness.dispatchMessage({
      type: "mm-offline/set-retention",
      scope: ALICE,
      retentionMs: 60_000,
    });
    vi.setSystemTime(START + 60 * 60_000);
    await harness.dispatchMessage({ type: "mm-offline/sweep", scope: ALICE });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY]).toBeUndefined();
    const cache = harness.cacheFor(ALICE_CACHE);
    expect(await cache?.match(PAGE_ONE)).toBeUndefined();
  });

  it("never deletes the chapter that is open, even when it is due", async () => {
    await saveAndFinish();
    // The reader sends mark-opened on mount, which both clears the timer and
    // marks this chapter as the one on screen.
    await harness.dispatchMessage({
      type: "mm-offline/mark-opened",
      scope: ALICE,
      key: KEY,
    });
    await harness.dispatchMessage({
      type: "mm-offline/set-retention",
      scope: ALICE,
      retentionMs: 60_000,
    });
    // Reaching the last page again while still on it: due, and on screen.
    vi.setSystemTime(START + 60 * 60_000);
    await harness.dispatchMessage({
      type: "mm-offline/mark-finished",
      scope: ALICE,
      key: KEY,
    });
    vi.setSystemTime(START + 120 * 60_000);
    await harness.dispatchMessage({ type: "mm-offline/sweep", scope: ALICE });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY]).toBeDefined();
  });

  it("can be turned off entirely", async () => {
    await saveAndFinish();
    await harness.dispatchMessage({
      type: "mm-offline/set-retention",
      scope: ALICE,
      retentionMs: null,
    });
    vi.setSystemTime(START + 30 * 24 * 60 * 60_000);
    await harness.dispatchMessage({ type: "mm-offline/sweep", scope: ALICE });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY]).toBeDefined();
  });

  it("evicts the oldest finished chapter under pressure", async () => {
    await saveAndFinish();
    await harness.dispatchMessage({
      type: "mm-offline/chapter-closed",
      key: KEY,
    });
    harness.estimate = { usage: 9_999_000_000, quota: 10_000_000_000 };
    await harness.dispatchMessage({ type: "mm-offline/sweep", scope: ALICE });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY]).toBeUndefined();
  });
});

describe("removal", () => {
  it("takes exactly what the chapter put there", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchMessage({
      type: "mm-offline/remove-chapter",
      scope: ALICE,
      key: KEY,
    });

    const cache = harness.cacheFor(ALICE_CACHE);
    expect(await cache?.match(PAGE_ONE)).toBeUndefined();
    expect(await cache?.match(PAGE_TWO)).toBeUndefined();
    expect(await cache?.match(PAYLOAD)).toBeUndefined();
    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY]).toBeUndefined();
  });

  it("clears one profile's caches without touching another's", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchMessage(
      { type: "mm-offline/set-scope", scope: BOB, apiBase: API_BASE },
      "client-b",
    );
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(BOB),
    }, "client-b");

    await harness.dispatchMessage({ type: "mm-offline/clear-scope", scope: BOB });

    expect(await harness.cacheNames()).toContain(ALICE_CACHE);
    expect(await harness.cacheNames()).not.toContain(BOB_CACHE);
  });
});

describe("downloading a novel", () => {
  /**
   * The spec calls a whole-series download mobile-only because "the web has no
   * on-device store". The web has this one, and a prose chapter fits it without
   * a new message, a new cache or a new rule: it is a `SaveChapterRequest` with
   * no images whose payload is `GET /novels/chapter`. This is that claim
   * executed rather than asserted — save it, cut the network, open it.
   */
  const NOVEL_SOURCE = "novelbin";
  const NOVEL_SERIES = "book/lotm";
  const NOVEL_CHAPTER = "ch/12";
  const NOVEL_KEY = `chapter:${NOVEL_SOURCE}:${NOVEL_SERIES}:${NOVEL_CHAPTER}`;
  const NOVEL_BODY = JSON.stringify({
    source_id: NOVEL_SOURCE,
    series_key: NOVEL_SERIES,
    chapter_key: NOVEL_CHAPTER,
    title: "Chapter 12",
    chapter_number: 12,
    paragraphs: ["The fog rolled in.", "Klein woke."],
    prev: "ch/11",
    next: "ch/13",
    word_count: 6,
  });

  function novelPayload() {
    return buildNovelSaveRequest({
      ref: {
        sourceId: NOVEL_SOURCE,
        seriesKey: NOVEL_SERIES,
        chapterKey: NOVEL_CHAPTER,
      },
      title: "Chapter 12",
      seriesTitle: "Lord of the Mysteries",
      scope: ALICE,
      apiBase: API_BASE,
      origin: ORIGIN,
      payloadJson: NOVEL_BODY,
    });
  }

  it("serves the chapter text with no network at all", async () => {
    await boot();
    const payload = novelPayload();
    route(harness, payload.documentUrl, { body: "<html>novel</html>" });
    await harness.dispatchMessage({ type: "mm-offline/save-chapter", payload });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({ url: payload.payloadUrl });
    expect(outcome.handled).toBe(true);
    expect(await outcome.response?.text()).toBe(NOVEL_BODY);
  });

  it("settles as ready — a chapter with no images has no pages to miss", async () => {
    await boot();
    const payload = novelPayload();
    route(harness, payload.documentUrl, { body: "<html>novel</html>" });
    await harness.dispatchMessage({ type: "mm-offline/save-chapter", payload });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[NOVEL_KEY]).toMatchObject({
      status: "ready",
      pageCount: 0,
      failed: 0,
      stale: false,
      // /downloads reads this to open prose in the novel reader. Without it the
      // row linked to the page reader, which answers "This chapter has no
      // pages." over bytes that are all present.
      medium: "novel",
    });
  });

  it("is never flagged stale by the page-drift check, which is about images", async () => {
    await boot();
    const payload = novelPayload();
    route(harness, payload.documentUrl, { body: "<html>novel</html>" });
    route(harness, payload.payloadUrl, { body: NOVEL_BODY });
    await harness.dispatchMessage({ type: "mm-offline/save-chapter", payload });

    // Online again: the live answer wins, and the saved copy is refreshed as it
    // passes. Prose carries no `pages`, so there is no drift to find.
    await harness.dispatchFetch({ url: payload.payloadUrl });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[NOVEL_KEY].stale).toBe(false);
  });

  it("opens a downloaded book cold, with the reader route never navigated to", async () => {
    await boot();
    const payload = novelPayload();
    route(harness, payload.documentUrl, { body: "<html>novel</html>" });
    await harness.dispatchMessage({ type: "mm-offline/save-chapter", payload });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: payload.documentUrl,
      mode: "navigate",
    });
    expect(await outcome.response?.text()).toBe("<html>novel</html>");
  });

  it("keeps one profile's book out of another's", async () => {
    await boot();
    const payload = novelPayload();
    route(harness, payload.documentUrl, { body: "<html>novel</html>" });
    await harness.dispatchMessage({ type: "mm-offline/save-chapter", payload });

    await harness.dispatchMessage(
      { type: "mm-offline/set-scope", scope: BOB, apiBase: API_BASE },
      "client-b",
    );
    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: payload.payloadUrl,
      clientId: "client-b",
    });
    // Handled, and refused: Bob's tab is answered from Bob's cache, which does
    // not exist — never from Alice's, and never from a shared default.
    expect(outcome.handled).toBe(true);
    expect(outcome.response?.ok).toBe(false);
    expect(await outcome.response?.text()).not.toContain("Klein");
  });
});

describe("drift after a re-list", () => {
  it("flags a saved chapter whose page urls moved", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    // A re-list reassigns the source's page URLs; every saved image is keyed by
    // the old ones.
    route(harness, PAYLOAD, {
      body: JSON.stringify({
        source_id: SOURCE,
        series_key: SERIES,
        chapter_key: CHAPTER,
        chapter_number: 50,
        page_count: 2,
        pages: [
          { number: 1, url: `${API_BASE}/sources/${SOURCE}/pages/x91/image` },
          { number: 2, url: `${API_BASE}/sources/${SOURCE}/pages/x92/image` },
        ],
        prev: "ch/49",
        next: "ch/51",
      }),
    });
    await harness.dispatchFetch({ url: PAYLOAD });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY].stale).toBe(true);
  });

  it("leaves an unchanged chapter alone", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchFetch({ url: PAYLOAD });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries[KEY].stale).toBe(false);
  });
});
