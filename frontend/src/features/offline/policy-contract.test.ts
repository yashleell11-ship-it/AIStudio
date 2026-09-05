import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * The service worker's decisions, tested against the file that actually ships.
 *
 * `public/sw-policy.js` is outside the TypeScript program — a worker cannot
 * import from `src/` — so the usual options are to test nothing or to test a
 * mirror that drifts. Instead the real source is read and executed here with a
 * stand-in `self`, which means every assertion below is about the code the
 * browser runs, not about a copy of it.
 */

const SOURCE = readFileSync(
  new URL("../../../public/sw-policy.js", import.meta.url),
  "utf8",
);

interface Scope {
  userId: number;
  profileId: number;
}

interface Entry {
  key: string;
  readAt: number | null;
}

interface Policy {
  RUNTIME_VERSION: string;
  CONTENT_VERSION: string;
  DEFAULT_RETENTION_MS: number;
  STORAGE_RESERVE_BYTES: number;
  SWR_ALLOWLIST: string[];
  OFFLINE_FALLBACK_ALLOWLIST: string[];
  SEARCH_PATHS: string[];
  SEARCH_QUERY_PARAMS: string[];
  INTERNAL_PREFIX: string;
  scopeToken(scope: unknown): string | null;
  shellCacheName(): string;
  staticCacheName(): string;
  pagesCacheName(): string;
  apiCacheName(scope: unknown): string | null;
  offlineCacheName(scope: unknown): string | null;
  parseCacheName(name: string): { kind: string; version: string; scope: string | null } | null;
  isObsoleteCacheName(name: string): boolean;
  selectObsoleteCaches(names: string[]): string[];
  selectScopeCaches(names: string[], scope: unknown): string[];
  apiPath(url: string, apiBase: string): string | null;
  isAuthUrl(url: string, apiBase: string | null): boolean;
  isSwrAllowedPath(path: string): boolean;
  isOfflineFallbackPath(path: string): boolean;
  hasSearchTerm(url: string): boolean;
  isSearchRequest(url: string, apiBase: string | null): boolean;
  isPageImagePath(path: string): boolean;
  isChapterManifestPath(path: string): boolean;
  classifyRequest(input: Record<string, unknown>): string;
  isCacheableResponse(response: unknown): boolean;
  responseSize(headers: unknown): number;
  selectExpiredKeys(
    index: unknown,
    now: number,
    options: { retentionMs?: number | null; protectKey?: string | null },
  ): string[];
  selectEvictionCandidates(index: unknown, options: { protectKey?: string | null }): string[];
  storagePressure(
    estimate: unknown,
    options: { reserveBytes?: number; maxUsageRatio?: number; incomingBytes?: number },
  ): {
    known: boolean;
    underPressure: boolean;
    usage: number;
    quota: number;
    free: number;
    ratio: number;
  };
}

function loadPolicy(): Policy {
  const factory = new Function("self", `${SOURCE}\nreturn self.MMOfflinePolicy;`);
  return factory({}) as Policy;
}

const policy = loadPolicy();

const ORIGIN = "https://manhwa.example";
const API = `${ORIGIN}/api`;
const ALICE: Scope = { userId: 1, profileId: 10 };
const BOB: Scope = { userId: 1, profileId: 11 };
const OTHER_ACCOUNT: Scope = { userId: 2, profileId: 10 };

function get(url: string, extra: Record<string, unknown> = {}): string {
  return policy.classifyRequest({
    method: "GET",
    url,
    mode: "cors",
    destination: "",
    hasRange: false,
    origin: ORIGIN,
    apiBase: API,
    ...extra,
  });
}

function index(entries: Entry[]) {
  const map: Record<string, Entry> = {};
  for (const entry of entries) map[entry.key] = entry;
  return { entries: map };
}

describe("scope isolation", () => {
  it("names the owner of a cache", () => {
    expect(policy.scopeToken(ALICE)).toBe("u1p10");
  });

  it("gives two profiles of one account different caches", () => {
    expect(policy.offlineCacheName(ALICE)).not.toBe(policy.offlineCacheName(BOB));
  });

  it("gives two accounts different caches even with the same profile id", () => {
    expect(policy.offlineCacheName(ALICE)).not.toBe(policy.offlineCacheName(OTHER_ACCOUNT));
  });

  it("has no cache at all without a scope, rather than a shared one", () => {
    expect(policy.offlineCacheName(null)).toBeNull();
    expect(policy.apiCacheName(null)).toBeNull();
    expect(policy.offlineCacheName({ userId: 1 })).toBeNull();
    expect(policy.offlineCacheName({ userId: 1, profileId: 0 })).toBeNull();
    expect(policy.offlineCacheName({ userId: 1, profileId: 1.5 })).toBeNull();
    expect(policy.offlineCacheName({ userId: "1", profileId: "2" })).toBeNull();
  });

  it("scopes the API cache too, so a shared GET cannot cross profiles", () => {
    expect(policy.apiCacheName(ALICE)).not.toBe(policy.apiCacheName(BOB));
  });

  it("collects every cache belonging to one profile and nobody else's", () => {
    const names = [
      policy.offlineCacheName(ALICE) as string,
      policy.apiCacheName(ALICE) as string,
      policy.offlineCacheName(BOB) as string,
      policy.shellCacheName(),
    ];
    expect(policy.selectScopeCaches(names, ALICE).sort()).toEqual(
      [policy.offlineCacheName(ALICE), policy.apiCacheName(ALICE)].sort(),
    );
  });
});

describe("cache generations", () => {
  it("round-trips its own names", () => {
    expect(policy.parseCacheName(policy.shellCacheName())).toEqual({
      kind: "shell",
      version: policy.RUNTIME_VERSION,
      scope: null,
    });
    expect(policy.parseCacheName(policy.offlineCacheName(ALICE) as string)).toEqual({
      kind: "offline",
      version: policy.CONTENT_VERSION,
      scope: "u1p10",
    });
  });

  it("never claims a cache it does not own", () => {
    expect(policy.parseCacheName("workbox-precache-v2")).toBeNull();
    expect(policy.isObsoleteCacheName("some-other-app-cache")).toBe(false);
    expect(policy.selectObsoleteCaches(["nextjs-data", "images"])).toEqual([]);
  });

  it("drops superseded runtime caches", () => {
    expect(policy.isObsoleteCacheName("mm-shell-v0")).toBe(true);
    expect(policy.isObsoleteCacheName("mm-pages-v0")).toBe(true);
    expect(policy.isObsoleteCacheName(policy.pagesCacheName())).toBe(false);
  });

  it("does not take saved chapters with it when the runtime version moves", () => {
    // The reason the two versions are separate: shipping a fix to a caching
    // rule must not delete somebody's downloaded reading.
    const saved = policy.offlineCacheName(ALICE) as string;
    expect(saved).not.toContain(policy.RUNTIME_VERSION);
    expect(policy.isObsoleteCacheName(saved)).toBe(false);
  });

  it("keeps another profile's current caches", () => {
    const names = [
      policy.offlineCacheName(ALICE) as string,
      policy.offlineCacheName(BOB) as string,
      "mm-shell-v0",
    ];
    expect(policy.selectObsoleteCaches(names)).toEqual(["mm-shell-v0"]);
  });

  it("drops saved caches from a superseded content generation", () => {
    expect(policy.isObsoleteCacheName("mm-offline-c0-u1p10")).toBe(true);
  });
});

describe("what may be cached", () => {
  it("never touches a mutation", () => {
    for (const method of ["POST", "PUT", "PATCH", "DELETE", "HEAD"]) {
      expect(get(`${API}/library/series`, { method })).toBe("bypass");
    }
  });

  it("never touches auth, in either URL shape", () => {
    expect(get(`${API}/auth/me`)).toBe("bypass");
    expect(get(`${API}/auth/bootstrap-status`)).toBe("bypass");
    // Even with no API base published, the production rewrite shape is known.
    expect(get(`${ORIGIN}/api/auth/me`, { apiBase: null })).toBe("bypass");
    expect(policy.isAuthUrl(`${API}/auth/login`, API)).toBe(true);
  });

  it("keeps auth out of the stale-while-revalidate allowlist by construction", () => {
    for (const entry of policy.SWR_ALLOWLIST) {
      expect(policy.isAuthUrl(`${API}${entry}`, API)).toBe(false);
    }
    expect(policy.isSwrAllowedPath("/auth/me")).toBe(false);
  });

  it("serves stale data only where stale data is harmless", () => {
    expect(get(`${API}/library/series?limit=20&offset=0`)).toBe("api-swr");
    expect(get(`${API}/library/series/12`)).toBe("api-swr");
    expect(get(`${API}/sources`)).toBe("api-swr");
  });

  it("never answers a search from a cache, whatever prefix it sits under", () => {
    // The regression this exists for: `/sources` is on the SWR list for the
    // installed-source catalogue, and allowlist entries match everything below
    // them, so the federated fan-out at `/sources/search` was answered
    // stale-first. Every search returned the PREVIOUS answer for that exact
    // query while the real one was fetched behind it and stored for next time —
    // results one search out of date, which reads as search being broken until
    // you search again.
    expect(get(`${API}/sources/search?q=a&page=1&per_page=40`)).toBe(
      "network-then-saved",
    );
    expect(get(`${API}/sources/search?q=solo%20leveling`)).toBe("network-then-saved");
    // A source's own search wears its listing endpoint, and is what the search
    // view's per-source Retry calls — stale-first made Retry a no-op.
    expect(get(`${API}/sources/asura/series?query=naruto`)).toBe("network-then-saved");
    expect(get(`${API}/library/series?search=naruto`)).toBe("network-then-saved");
    expect(policy.isSearchRequest(`${API}/sources/search?q=a`, API)).toBe(true);
  });

  it("still serves the catalogue reads those endpoints also answer", () => {
    // The rule is about the typed term, not the path: without one these are the
    // unfiltered listings they always were, and stale-first is right for them.
    expect(get(`${API}/sources`)).toBe("api-swr");
    expect(get(`${API}/sources/asura/series?page=2`)).toBe("api-swr");
    expect(get(`${API}/library/series?limit=20&offset=0`)).toBe("api-swr");
    // A present-but-blank term is not a search either.
    expect(get(`${API}/library/series?search=`)).toBe("api-swr");
    expect(get(`${API}/library/series?search=%20`)).toBe("api-swr");
    expect(policy.hasSearchTerm(`${API}/library/series?search=`)).toBe(false);
  });

  it("recognises a typed term under every name this API gives one", () => {
    // `q` (federated and OCR search), `query` (a source's own listing) and
    // `search` (the library list) are the three, and adding a fourth without
    // listing it here is how this bug comes back.
    for (const name of policy.SEARCH_QUERY_PARAMS) {
      expect(policy.hasSearchTerm(`${API}/anything?${name}=naruto`)).toBe(true);
    }
    expect(policy.hasSearchTerm(`${API}/anything?page=2&per_page=40`)).toBe(false);
  });

  it("never serves stale reading progress, which would rewind the reader", () => {
    expect(get(`${API}/reader/progress/12`)).toBe("network-then-saved");
    expect(policy.isSwrAllowedPath("/reader/progress/12")).toBe(false);
  });

  it("never serves a stale chapter manifest, whose page urls move on a re-list", () => {
    expect(
      get(`${API}/reader/chapter/manifest?source=asura&series=s%2Fk&chapter=c%2F9`),
    ).toBe("network-then-saved");
    expect(policy.isChapterManifestPath("/reader/chapter/manifest")).toBe(true);
    expect(policy.isSwrAllowedPath("/reader/chapter/manifest")).toBe(false);
  });

  it("keeps the bookmark listing readable with no signal, but never stale-first", () => {
    // Network-first with a stored fallback, NOT stale-while-revalidate: the
    // reader writes to this list from inside the app, and a cache-first answer
    // would drop the bookmark just made or resurrect the one just deleted.
    expect(get(`${API}/reader/bookmarks`)).toBe("api-offline-fallback");
    expect(policy.isSwrAllowedPath("/reader/bookmarks")).toBe(false);
  });

  it("keeps the two API cache lists disjoint, so a path has one strategy", () => {
    for (const entry of policy.OFFLINE_FALLBACK_ALLOWLIST) {
      expect(policy.isSwrAllowedPath(entry)).toBe(false);
      expect(policy.isAuthUrl(`${API}${entry}`, API)).toBe(false);
    }
    for (const entry of policy.SWR_ALLOWLIST) {
      expect(policy.isOfflineFallbackPath(entry)).toBe(false);
    }
  });

  it("still never caches a mutation on a fallback path", () => {
    // Deleting a bookmark is `DELETE /reader/bookmarks/{id}` — same prefix,
    // and rule 1 has to win over the allowlist.
    expect(get(`${API}/reader/bookmarks/7`, { method: "DELETE" })).toBe("bypass");
    expect(get(`${API}/reader/bookmark`, { method: "POST" })).toBe("bypass");
  });

  it("does not widen an allowlist entry into a sibling path", () => {
    expect(policy.isSwrAllowedPath("/library/series")).toBe(true);
    expect(policy.isSwrAllowedPath("/library/series/4")).toBe(true);
    expect(policy.isSwrAllowedPath("/library/series-private")).toBe(false);
    expect(policy.isSwrAllowedPath("/library/collections")).toBe(false);
    expect(policy.isOfflineFallbackPath("/reader/bookmarks")).toBe(true);
    expect(policy.isOfflineFallbackPath("/reader/bookmarks-shared")).toBe(false);
    expect(policy.isOfflineFallbackPath("/reader/bookmark")).toBe(false);
  });

  it("answers a saved page image from the device first, by URL shape or by destination", () => {
    // The source-proxy page endpoint is recognised on its path alone — it lives
    // under `/sources/…`, which the SWR allowlist also matches, so this must win.
    expect(get(`${API}/sources/asura/pages/vol1%2Fp551/image`)).toBe("saved-first");
    expect(policy.isPageImagePath("/sources/asura/pages/vol1%2Fp551/image")).toBe(true);
    expect(policy.isPageImagePath("/sources/asura")).toBe(false);
    // Any other API image (a cover, say) still goes saved-first via destination.
    expect(
      get(`${API}/sources/asura/series/s%2Fk/cover`, { destination: "image" }),
    ).toBe("saved-first");
  });

  it("takes build assets cache-first and only when they are ours", () => {
    expect(get(`${ORIGIN}/_next/static/chunks/main-abc123.js`)).toBe("static");
    expect(get(`${ORIGIN}/icons/icon-192.png`)).toBe("static");
    expect(get("https://cdn.example.com/_next/static/x.js")).toBe("bypass");
  });

  it("handles same-origin navigations and leaves other origins alone", () => {
    expect(get(`${ORIGIN}/reader/3/9`, { mode: "navigate" })).toBe("navigation");
    expect(get("https://elsewhere.example/page", { mode: "navigate" })).toBe("bypass");
  });

  it("stays out of the way of range requests and non-http schemes", () => {
    expect(get(`${API}/sources/asura/pages/p1/image`, { hasRange: true })).toBe("bypass");
    expect(get("chrome-extension://abcd/inject.js")).toBe("bypass");
  });

  it("ignores its own bookkeeping keys", () => {
    expect(get(`${ORIGIN}${policy.INTERNAL_PREFIX}index.json`)).toBe("bypass");
  });

  it("stores only complete, readable, successful responses", () => {
    expect(policy.isCacheableResponse({ status: 200, type: "basic" })).toBe(true);
    expect(policy.isCacheableResponse({ status: 404, type: "basic" })).toBe(false);
    expect(policy.isCacheableResponse({ status: 206, type: "basic" })).toBe(false);
    // An opaque response has an unreadable status: caching one means caching a
    // failure that can never be told from a success.
    expect(policy.isCacheableResponse({ status: 0, type: "opaque" })).toBe(false);
    expect(policy.isCacheableResponse({ status: 200, type: "basic", redirected: true })).toBe(
      false,
    );
  });

  it("reads a stored response's size from its own headers", () => {
    expect(policy.responseSize({ get: () => "2048" })).toBe(2048);
    expect(policy.responseSize({ get: () => null })).toBe(0);
    expect(policy.responseSize(null)).toBe(0);
  });
});

describe("the 2-day rule", () => {
  const NOW = 1_700_000_000_000;
  const THREE_DAYS_AGO = NOW - 3 * 24 * 60 * 60 * 1000;
  const ONE_HOUR_AGO = NOW - 60 * 60 * 1000;

  it("expires a finished chapter once the timer has run out", () => {
    const keys = policy.selectExpiredKeys(
      index([{ key: "chapter:1", readAt: THREE_DAYS_AGO }]),
      NOW,
      {},
    );
    expect(keys).toEqual(["chapter:1"]);
  });

  it("leaves a finished chapter alone until then", () => {
    expect(
      policy.selectExpiredKeys(index([{ key: "chapter:1", readAt: ONE_HOUR_AGO }]), NOW, {}),
    ).toEqual([]);
  });

  it("never expires a chapter that was never finished, however old", () => {
    // Trigger is `read_complete`, not "has been sitting there a while".
    expect(
      policy.selectExpiredKeys(index([{ key: "chapter:1", readAt: null }]), NOW, {}),
    ).toEqual([]);
  });

  it("treats reopening as cancelling the timer", () => {
    // The worker clears readAt on open; with it cleared nothing is due.
    const reopened = index([{ key: "chapter:1", readAt: null }]);
    expect(policy.selectExpiredKeys(reopened, NOW, {})).toEqual([]);
  });

  it("never deletes the chapter that is open, even when it is due", () => {
    expect(
      policy.selectExpiredKeys(index([{ key: "chapter:1", readAt: THREE_DAYS_AGO }]), NOW, {
        protectKey: "chapter:1",
      }),
    ).toEqual([]);
  });

  it("can be turned off without a rebuild", () => {
    expect(
      policy.selectExpiredKeys(index([{ key: "chapter:1", readAt: THREE_DAYS_AGO }]), NOW, {
        retentionMs: null,
      }),
    ).toEqual([]);
  });

  it("defaults to the owner's 48 hours", () => {
    expect(policy.DEFAULT_RETENTION_MS).toBe(48 * 60 * 60 * 1000);
  });
});

describe("eviction under pressure", () => {
  it("only ever offers finished chapters", () => {
    const candidates = policy.selectEvictionCandidates(
      index([
        { key: "unread", readAt: null },
        { key: "read", readAt: 5 },
      ]),
      {},
    );
    // Stalling at the floor is the deliberate choice: silently deleting
    // something nobody has read is worse than refusing to save more.
    expect(candidates).toEqual(["read"]);
  });

  it("takes the oldest finished chapter first", () => {
    const candidates = policy.selectEvictionCandidates(
      index([
        { key: "newest", readAt: 300 },
        { key: "oldest", readAt: 100 },
        { key: "middle", readAt: 200 },
      ]),
      {},
    );
    expect(candidates).toEqual(["oldest", "middle", "newest"]);
  });

  it("never offers the chapter that is open", () => {
    expect(
      policy.selectEvictionCandidates(index([{ key: "chapter:7", readAt: 1 }]), {
        protectKey: "chapter:7",
      }),
    ).toEqual([]);
  });
});

describe("storage pressure", () => {
  const GB = 1024 * 1024 * 1024;

  it("reports no pressure when the browser will not say", () => {
    expect(policy.storagePressure(null, {}).known).toBe(false);
    expect(policy.storagePressure({ usage: 1 }, {}).underPressure).toBe(false);
  });

  it("is relaxed with room to spare", () => {
    const pressure = policy.storagePressure({ usage: 1 * GB, quota: 10 * GB }, {});
    expect(pressure.underPressure).toBe(false);
    expect(pressure.free).toBe(9 * GB);
  });

  it("bites when the reserve would be eaten into", () => {
    const pressure = policy.storagePressure(
      { usage: 10 * GB - policy.STORAGE_RESERVE_BYTES / 2, quota: 10 * GB },
      {},
    );
    expect(pressure.underPressure).toBe(true);
  });

  it("bites on the ratio even when the absolute headroom looks large", () => {
    expect(
      policy.storagePressure({ usage: 950 * GB, quota: 1000 * GB }, {}).underPressure,
    ).toBe(true);
  });

  it("counts what is about to be written, not just what is written", () => {
    const before = policy.storagePressure({ usage: 8 * GB, quota: 10 * GB }, {});
    const after = policy.storagePressure(
      { usage: 8 * GB, quota: 10 * GB },
      { incomingBytes: 1.9 * GB },
    );
    expect(before.underPressure).toBe(false);
    expect(after.underPressure).toBe(true);
  });
});
