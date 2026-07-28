import { beforeEach, describe, expect, it } from "vitest";
import {
  API_BASE,
  ORIGIN,
  createHarness,
  readIndex,
  route,
  type Harness,
} from "./sw-harness.testing";

/**
 * The service worker, executed.
 *
 * `policy-contract.test.ts` proves the worker decides correctly; this proves it
 * then does what it decided — which cache the bytes land in, what comes back
 * with the network down, and what a profile switch can and cannot see. Those
 * are the failures that would only otherwise be found on a train.
 */

const ALICE = { userId: 1, profileId: 10 };
const BOB = { userId: 1, profileId: 11 };
const ALICE_CACHE = "mm-offline-c1-u1p10";
const BOB_CACHE = "mm-offline-c1-u1p11";

const PAGE_ONE = `${API_BASE}/reader/page/1/image`;
const PAGE_TWO = `${API_BASE}/reader/page/2/image`;
const PAYLOAD = `${API_BASE}/reader/chapter/50`;

const CHAPTER_BODY = JSON.stringify({ id: 50, pages: [{ id: 1 }, { id: 2 }] });

function savePayload(scope: { userId: number; profileId: number }) {
  return {
    key: "chapter:50",
    chapterId: "50",
    seriesId: "7",
    title: "Chapter 50",
    seriesTitle: "Solo Levelling",
    scope,
    profileId: scope.profileId,
    documentUrl: `${ORIGIN}/reader/7/50`,
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
  route(harness, "/offline", { body: "<html>offline library</html>" });
  route(harness, PAGE_ONE, { body: "page-one-bytes", headers: { "content-type": "image/jpeg" } });
  route(harness, PAGE_TWO, { body: "page-two-bytes", headers: { "content-type": "image/jpeg" } });
  route(harness, PAYLOAD, { body: CHAPTER_BODY });
  route(harness, `${ORIGIN}/reader/7/50`, { body: "<html>reader</html>" });
});

describe("install and activate", () => {
  it("precaches the offline fallback so there is always something to render", async () => {
    await harness.dispatchInstall();
    const shell = harness.cacheFor("mm-shell-v1");
    expect(await shell?.match("/offline-fallback.html")).toBeTruthy();
  });

  it("warms the installed app's start_url", async () => {
    await harness.dispatchInstall();
    await harness.dispatchActivate();
    const pages = harness.cacheFor("mm-pages-v1");
    expect(await pages?.match("/library")).toBeTruthy();
  });

  it("warms /offline, the one page the offline fallback links to", async () => {
    await harness.dispatchInstall();
    await harness.dispatchActivate();
    const pages = harness.cacheFor("mm-pages-v1");
    expect(await pages?.match("/offline")).toBeTruthy();
  });

  it("drops a superseded generation but never another profile's downloads", async () => {
    await harness.storage.open("mm-shell-v0");
    await harness.storage.open(BOB_CACHE);
    await harness.storage.open("some-other-app");
    await harness.dispatchInstall();
    await harness.dispatchActivate();

    const names = await harness.cacheNames();
    expect(names).not.toContain("mm-shell-v0");
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
    expect(await cache?.match(`${ORIGIN}/reader/7/50`)).toBeTruthy();

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries["chapter:50"].status).toBe("ready");
    expect(index?.entries["chapter:50"].savedPages).toBe(2);
    expect(index?.entries["chapter:50"].bytes).toBeGreaterThan(0);
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
    expect(index?.entries["chapter:50"].status).toBe("partial");
    expect(index?.entries["chapter:50"].savedPages).toBe(1);
    expect(index?.entries["chapter:50"].failed).toBe(1);
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
    expect(index?.entries["chapter:50"].status).toBe("paused");
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

  it("serves the saved chapter payload so the reader can render at all", async () => {
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
    // reader inside the SPA, so the browser NEVER issued a navigation for
    // /reader/7/50 and the document cache has no copy of it. Saving fetches the
    // document on purpose for exactly this case; a cold offline launch (or a
    // reload on the train) must get it back rather than the offline page.
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: `${ORIGIN}/reader/7/50`,
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
      url: `${ORIGIN}/reader/7/50`,
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
    const pages = harness.cacheFor("mm-pages-v1");
    expect((await (pages as { keys(): Promise<unknown[]> }).keys()).length).toBeLessThanOrEqual(
      60,
    );
    // The most recent visits survive; the oldest are the ones dropped.
    expect(await pages?.match(`${ORIGIN}/library/69`)).toBeTruthy();
    expect(await pages?.match(`${ORIGIN}/library/0`)).toBeUndefined();
  });

  it("ignores the query string when matching a cached reader document", async () => {
    await boot();
    await harness.dispatchFetch({ url: `${ORIGIN}/reader/7/50`, mode: "navigate" });

    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: `${ORIGIN}/reader/7/50?page=12`,
      mode: "navigate",
    });
    expect(await outcome.response?.text()).toBe("<html>reader</html>");
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
    expect(await harness.cacheNames()).toContain("mm-api-v1-u1p10");
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
  async function saveAndFinish(): Promise<void> {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchMessage({
      type: "mm-offline/mark-finished",
      scope: ALICE,
      key: "chapter:50",
    });
  }

  it("stamps a finish time and clears it when the chapter is reopened", async () => {
    await saveAndFinish();
    let index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries["chapter:50"].readAt).toBeGreaterThan(0);

    await harness.dispatchMessage({
      type: "mm-offline/mark-opened",
      scope: ALICE,
      key: "chapter:50",
    });
    index = await readIndex(harness, ALICE_CACHE);
    // Re-reading cancels the deletion instead of it vanishing mid-scroll.
    expect(index?.entries["chapter:50"].readAt).toBeNull();
  });

  it("deletes a finished chapter's pages once its retention has passed", async () => {
    await saveAndFinish();
    // Retention of a single millisecond: already elapsed by the sweep.
    await harness.dispatchMessage({
      type: "mm-offline/set-retention",
      scope: ALICE,
      retentionMs: 1,
    });
    await harness.dispatchMessage({ type: "mm-offline/sweep", scope: ALICE });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries["chapter:50"]).toBeUndefined();
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
      key: "chapter:50",
    });
    await harness.dispatchMessage({
      type: "mm-offline/set-retention",
      scope: ALICE,
      retentionMs: 1,
    });
    // Reaching the last page again while still on it: due, and on screen.
    await harness.dispatchMessage({
      type: "mm-offline/mark-finished",
      scope: ALICE,
      key: "chapter:50",
    });
    await harness.dispatchMessage({ type: "mm-offline/sweep", scope: ALICE });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries["chapter:50"]).toBeDefined();
  });

  it("can be turned off entirely", async () => {
    await saveAndFinish();
    await harness.dispatchMessage({
      type: "mm-offline/set-retention",
      scope: ALICE,
      retentionMs: null,
    });
    await harness.dispatchMessage({ type: "mm-offline/sweep", scope: ALICE });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries["chapter:50"]).toBeDefined();
  });

  it("evicts the oldest finished chapter under pressure", async () => {
    await saveAndFinish();
    await harness.dispatchMessage({
      type: "mm-offline/chapter-closed",
      key: "chapter:50",
    });
    harness.estimate = { usage: 9_999_000_000, quota: 10_000_000_000 };
    await harness.dispatchMessage({ type: "mm-offline/sweep", scope: ALICE });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries["chapter:50"]).toBeUndefined();
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
      key: "chapter:50",
    });

    const cache = harness.cacheFor(ALICE_CACHE);
    expect(await cache?.match(PAGE_ONE)).toBeUndefined();
    expect(await cache?.match(PAGE_TWO)).toBeUndefined();
    expect(await cache?.match(PAYLOAD)).toBeUndefined();
    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries["chapter:50"]).toBeUndefined();
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
      payload: { ...savePayload(BOB), key: "chapter:50" },
    }, "client-b");

    await harness.dispatchMessage({ type: "mm-offline/clear-scope", scope: BOB });

    expect(await harness.cacheNames()).toContain(ALICE_CACHE);
    expect(await harness.cacheNames()).not.toContain(BOB_CACHE);
  });
});

describe("drift after a rescan", () => {
  it("flags a saved chapter whose page ids moved", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });

    // A rescan reassigns page ids; every saved image is keyed by the old ones.
    route(harness, PAYLOAD, {
      body: JSON.stringify({ id: 50, pages: [{ id: 91 }, { id: 92 }] }),
    });
    await harness.dispatchFetch({ url: PAYLOAD });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries["chapter:50"].stale).toBe(true);
  });

  it("leaves an unchanged chapter alone", async () => {
    await boot();
    await harness.dispatchMessage({
      type: "mm-offline/save-chapter",
      payload: savePayload(ALICE),
    });
    await harness.dispatchFetch({ url: PAYLOAD });

    const index = await readIndex(harness, ALICE_CACHE);
    expect(index?.entries["chapter:50"].stale).toBe(false);
  });
});
