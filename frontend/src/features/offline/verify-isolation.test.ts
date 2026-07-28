/**
 * Independent adversarial isolation checks against the shipping worker.
 *
 * Written during verification to probe the paths `sw-integration.test.ts` does
 * NOT cover: what answers a request whose client the worker does not recognise.
 * A fetch event names its client, but a NAVIGATION does not — `event.clientId`
 * is empty for a document load, because the client that will render it does not
 * exist yet. The worker therefore falls back to `persistedState`, which is
 * whatever tab published last. With two profiles open in two tabs that fallback
 * is the one place a cross-profile answer could come from, so it is pinned here.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  API_BASE,
  ORIGIN,
  createHarness,
  route,
  type Harness,
} from "./sw-harness.testing";

const A = { userId: 1, profileId: 1 };
const B = { userId: 2, profileId: 2 };

async function boot(): Promise<Harness> {
  const harness = createHarness();
  harness.clients = [
    { id: "tab-a", messages: [] },
    { id: "tab-b", messages: [] },
  ];
  await harness.dispatchInstall();
  await harness.dispatchActivate();
  return harness;
}

async function publish(
  harness: Harness,
  scope: { userId: number; profileId: number } | null,
  clientId: string,
): Promise<void> {
  await harness.dispatchMessage(
    { type: "mm-offline/set-scope", scope, apiBase: API_BASE },
    clientId,
  );
}

describe("unknown-client fallback cannot leak per-profile API data", () => {
  it("never answers an SWR request from another profile's cache when the client is unknown", async () => {
    const harness = await boot();
    await publish(harness, A, "tab-a");

    // Profile A caches a library listing.
    route(harness, `${API_BASE}/library/series`, { body: '{"secret":"A"}' });
    await harness.dispatchFetch({ url: `${API_BASE}/library/series`, clientId: "tab-a" });

    // Profile B publishes last, so it owns `persistedState`.
    await publish(harness, B, "tab-b");

    // A request from a client the worker has never seen, offline so only a
    // cache could answer it. It must NOT be handed profile A's body.
    harness.offline = true;
    const outcome = await harness.dispatchFetch({
      url: `${API_BASE}/library/series`,
      clientId: "ghost-tab",
    });
    const body = outcome.response ? await outcome.response.text().catch(() => "") : "";
    expect(body).not.toContain("A");
  });

  it("keeps each tab on its own API cache after the other tab switches profile", async () => {
    const harness = await boot();
    await publish(harness, A, "tab-a");
    route(harness, `${API_BASE}/sources`, { body: '{"who":"A"}' });
    await harness.dispatchFetch({ url: `${API_BASE}/sources`, clientId: "tab-a" });

    await publish(harness, B, "tab-b");
    route(harness, `${API_BASE}/sources`, { body: '{"who":"B"}' });
    await harness.dispatchFetch({ url: `${API_BASE}/sources`, clientId: "tab-b" });

    harness.offline = true;
    const fromB = await harness.dispatchFetch({
      url: `${API_BASE}/sources`,
      clientId: "tab-b",
    });
    expect(await fromB.response!.text()).toContain("B");

    const fromA = await harness.dispatchFetch({
      url: `${API_BASE}/sources`,
      clientId: "tab-a",
    });
    expect(await fromA.response!.text()).toContain("A");
  });

  it("stops answering from cache once the same tab switches to another profile", async () => {
    const harness = await boot();
    await publish(harness, A, "tab-a");
    route(harness, `${API_BASE}/sources`, { body: '{"who":"A"}' });
    await harness.dispatchFetch({ url: `${API_BASE}/sources`, clientId: "tab-a" });

    // Same tab, now a different profile.
    await publish(harness, B, "tab-a");
    harness.offline = true;
    const after = await harness.dispatchFetch({
      url: `${API_BASE}/sources`,
      clientId: "tab-a",
    });
    const body = after.response ? await after.response.text().catch(() => "") : "";
    expect(body).not.toContain("A");
  });

  it("caches nothing per-profile once the scope is cleared to null", async () => {
    const harness = await boot();
    await publish(harness, A, "tab-a");
    route(harness, `${API_BASE}/sources`, { body: '{"who":"A"}' });
    await harness.dispatchFetch({ url: `${API_BASE}/sources`, clientId: "tab-a" });

    await publish(harness, null, "tab-a");
    harness.offline = true;
    const after = await harness.dispatchFetch({
      url: `${API_BASE}/sources`,
      clientId: "tab-a",
    });
    const body = after.response ? await after.response.text().catch(() => "") : "";
    expect(body).not.toContain("A");
  });
});

describe("mutations and auth stay untouched under every scope state", () => {
  it("declines every mutating method even on an allowlisted path", async () => {
    const harness = await boot();
    await publish(harness, A, "tab-a");
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      const outcome = await harness.dispatchFetch({
        url: `${API_BASE}/library/series`,
        method,
        clientId: "tab-a",
      });
      expect(outcome.handled, `${method} was intercepted`).toBe(false);
    }
    const names = await harness.cacheNames();
    for (const name of names) {
      const cache = harness.cacheFor(name)!;
      for (const key of cache.entries.keys()) {
        expect(key).not.toContain("/library/series");
      }
    }
  });

  it("declines auth GETs whether or not a profile is published", async () => {
    for (const scope of [A, null]) {
      const harness = await boot();
      await publish(harness, scope, "tab-a");
      for (const path of ["/auth", "/auth/me", "/auth/login?next=/library"]) {
        const outcome = await harness.dispatchFetch({
          url: `${API_BASE}${path}`,
          clientId: "tab-a",
        });
        expect(outcome.handled, `${path} was intercepted`).toBe(false);
      }
    }
  });

  it("stores no auth response in any cache after an auth request", async () => {
    const harness = await boot();
    await publish(harness, A, "tab-a");
    route(harness, `${API_BASE}/auth/me`, { body: '{"email":"private@example.com"}' });
    await harness.dispatchFetch({ url: `${API_BASE}/auth/me`, clientId: "tab-a" });
    for (const name of await harness.cacheNames()) {
      const cache = harness.cacheFor(name)!;
      for (const key of cache.entries.keys()) {
        expect(key).not.toContain("/auth");
      }
    }
  });
});

describe("the update path cannot strand a reader on a stale shell", () => {
  it("calls skipWaiting only from the message handler, never from install", () => {
    // Asserted against the source because the harness does not record the call:
    // the property being verified is *where* skipWaiting may appear, and an
    // install listener that claims control is exactly how a reader gets a new
    // bundle swapped in mid-chapter without being asked.
    const source = readFileSync(
      new URL("../../../public/sw.js", import.meta.url),
      "utf8",
    );
    const installBody = source.slice(
      source.indexOf('addEventListener("install"'),
      source.indexOf('addEventListener("activate"'),
    );
    expect(installBody.length).toBeGreaterThan(0);
    // `skipWaiting(` and not `skipWaiting`: the install listener carries a
    // comment explaining its own absence, and matching prose would fail on it.
    expect(installBody).not.toContain("skipWaiting(");

    const skipCalls = source.match(/self\.skipWaiting\(\)/g) ?? [];
    expect(skipCalls).toHaveLength(1);
    // The single call site sits under the page-initiated message.
    const callIndex = source.indexOf("self.skipWaiting()");
    expect(source.lastIndexOf("mm-offline/skip-waiting", callIndex)).toBeGreaterThan(-1);
  });

  it("serves a fresh document over a cached one whenever the network answers", async () => {
    const harness = await boot();
    await publish(harness, A, "tab-a");
    route(harness, `${ORIGIN}/library`, { body: "<html>old</html>" });
    await harness.dispatchFetch({ url: `${ORIGIN}/library`, mode: "navigate" });

    route(harness, `${ORIGIN}/library`, { body: "<html>new</html>" });
    const again = await harness.dispatchFetch({
      url: `${ORIGIN}/library`,
      mode: "navigate",
    });
    expect(await again.response!.text()).toBe("<html>new</html>");
  });
});
