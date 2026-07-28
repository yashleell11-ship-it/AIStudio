/*
 * ManhwaManiacs service worker — POLICY.
 *
 * Every decision the worker makes that can be decided from data alone lives
 * here: cache naming, which requests may be cached and how, which saved
 * chapters may be deleted and when. `sw.js` next to this file holds the parts
 * that must touch the network and Cache Storage, and nothing else.
 *
 * WHY IT IS A SEPARATE PLAIN SCRIPT: a service worker is not part of the
 * Next.js bundle, so it cannot import from `src/`. Rather than write the rules
 * twice — once in the worker and once in a TypeScript mirror that drifts — the
 * rules are written once, here, as dependency-free ES5-ish JavaScript that
 * `sw.js` pulls in with `importScripts()` and that
 * `src/features/offline/policy-contract.test.ts` evaluates directly. The tests
 * therefore exercise the code that actually ships, not a copy of it.
 *
 * A service worker that caches wrongly is worse than none, so the two rules
 * that keep this recoverable are stated up front:
 *   1. Only GET is ever cached. A POST/PATCH/PUT/DELETE is never stored and
 *      never answered from a cache.
 *   2. Anything under the API's /auth/* is never stored and never answered
 *      from a cache, in any strategy, at any layer.
 */

(function attachPolicy(global) {
  "use strict";

  /**
   * Runtime cache generation. Bumping it drops the shell, static, page and API
   * caches on the next activate — the escape hatch when a caching rule turns
   * out to be wrong in production. It deliberately does NOT appear in the name
   * of a saved-chapter cache: a bad rule must be fixable without deleting
   * somebody's downloaded reading.
   */
  var RUNTIME_VERSION = "v1";

  /**
   * Saved-content generation. Bump ONLY when the on-disk shape of a saved
   * chapter changes in a way the reader cannot read back, because bumping it
   * abandons every chapter the user has saved.
   */
  var CONTENT_VERSION = "c1";

  var PREFIX = "mm";

  /** Cache keys the app never requests over the network; ours to write. */
  var INTERNAL_PREFIX = "/__mm-offline/";
  var INDEX_KEY = INTERNAL_PREFIX + "index.json";
  var STATE_KEY = INTERNAL_PREFIX + "state.json";

  /** The 2-day rule from docs/OFFLINE_READING.md, in milliseconds. */
  var DEFAULT_RETENTION_MS = 48 * 60 * 60 * 1000;

  /**
   * Storage headroom. The native design reserves a fixed 1.5 GB of *disk*; a
   * browser instead hands out a quota, so the equivalent brake is a fraction of
   * that quota plus a floor. Saving stops before either is crossed.
   */
  var STORAGE_RESERVE_BYTES = 250 * 1024 * 1024;
  var MAX_USAGE_RATIO = 0.9;

  /**
   * API GET paths (relative to the API base) that may be answered from cache
   * while a fresh copy is fetched in the background. The bar is "a reader
   * shown the previous answer for a few seconds is not harmed".
   *
   * Deliberately NOT here, each for its own reason:
   *   /auth/*            — session identity; see the header of this file.
   *   /reader/progress/* — a stale resume point silently rewinds the reader.
   *                        docs/OFFLINE_READING.md picks furthest-wins merging
   *                        precisely to stop that happening.
   *   /reader/chapter/*  — page ids are reassigned on rescan, so a stale
   *                        payload points at images that may no longer be that
   *                        page. Only an explicit "save for offline" caches
   *                        these, and it re-validates them (see sw.js).
   *   /updates*          — the entire value of the updates feed is freshness.
   *   /downloads*        — queue state; stale shows a finished job as running.
   *   /settings*, /system*, /admin* — instance state; stale health is a lie.
   */
  var SWR_ALLOWLIST = ["/library/series", "/sources"];

  /** Same-origin path prefixes safe to serve cache-first. */
  var IMMUTABLE_PREFIXES = [
    // Content-hashed by the Next.js build — the URL changes when the bytes do,
    // so a hit can never be stale. Self-hosted fonts land here too.
    "/_next/static/",
    "/icons/",
  ];

  function isNonEmptyString(value) {
    return typeof value === "string" && value.length > 0;
  }

  function isPositiveInteger(value) {
    return typeof value === "number" && Number.isInteger(value) && value > 0;
  }

  /**
   * The cache-name fragment identifying one (user, profile), or null when
   * either half is missing or malformed.
   *
   * Saved chapters are per-persona exactly like the library they came from, so
   * the scope is part of the cache NAME, not a field inside it: two profiles
   * cannot end up reading each other's saved pages by URL collision because
   * they are never looking in the same cache. No scope yields no token, and
   * every caller treats a null token as "no cache at all" rather than falling
   * back to a shared one.
   */
  function scopeToken(scope) {
    if (!scope || typeof scope !== "object") return null;
    if (!isPositiveInteger(scope.userId) || !isPositiveInteger(scope.profileId)) {
      return null;
    }
    return "u" + scope.userId + "p" + scope.profileId;
  }

  function shellCacheName() {
    return PREFIX + "-shell-" + RUNTIME_VERSION;
  }

  function staticCacheName() {
    return PREFIX + "-static-" + RUNTIME_VERSION;
  }

  function pagesCacheName() {
    return PREFIX + "-pages-" + RUNTIME_VERSION;
  }

  function stateCacheName() {
    return PREFIX + "-state-" + RUNTIME_VERSION;
  }

  /** Per-scope API cache. Null without a scope: nothing per-profile is cached. */
  function apiCacheName(scope) {
    var token = scopeToken(scope);
    return token === null ? null : PREFIX + "-api-" + RUNTIME_VERSION + "-" + token;
  }

  /** Per-scope saved-chapter cache. Null without a scope. */
  function offlineCacheName(scope) {
    var token = scopeToken(scope);
    return token === null ? null : PREFIX + "-offline-" + CONTENT_VERSION + "-" + token;
  }

  /**
   * Split one of our cache names back into its parts, or null if the name is
   * not ours. Used on activate so a foreign cache is never deleted.
   */
  function parseCacheName(name) {
    if (!isNonEmptyString(name)) return null;
    var parts = name.split("-");
    if (parts.length < 3 || parts[0] !== PREFIX) return null;
    return {
      kind: parts[1],
      version: parts[2],
      scope: parts.length > 3 ? parts.slice(3).join("-") : null,
    };
  }

  /**
   * Caches to delete on activate: ours, but from a superseded generation.
   *
   * Saved-chapter caches are judged against CONTENT_VERSION and every other
   * cache against RUNTIME_VERSION, which is what lets a caching bug be shipped
   * out without taking the user's downloads with it. Another profile's
   * current-generation caches are kept — they are not stale, they are someone
   * else's.
   */
  function isObsoleteCacheName(name) {
    var parsed = parseCacheName(name);
    if (parsed === null) return false;
    if (parsed.kind === "offline") return parsed.version !== CONTENT_VERSION;
    return parsed.version !== RUNTIME_VERSION;
  }

  function selectObsoleteCaches(names) {
    var out = [];
    for (var i = 0; i < (names || []).length; i += 1) {
      if (isObsoleteCacheName(names[i])) out.push(names[i]);
    }
    return out;
  }

  /** Every cache belonging to one scope — what "forget this profile" deletes. */
  function selectScopeCaches(names, scope) {
    var token = scopeToken(scope);
    var out = [];
    if (token === null) return out;
    for (var i = 0; i < (names || []).length; i += 1) {
      var parsed = parseCacheName(names[i]);
      if (parsed !== null && parsed.scope === token) out.push(names[i]);
    }
    return out;
  }

  function safeUrl(url) {
    try {
      return new URL(url);
    } catch {
      return null;
    }
  }

  /**
   * The path of `url` relative to the API base, or null when it is not an API
   * URL. `apiBase` is published by the client because only it knows whether the
   * backend is same-origin (`/api`, production) or a separate dev origin.
   */
  function apiPath(url, apiBase) {
    if (!isNonEmptyString(url) || !isNonEmptyString(apiBase)) return null;
    var base = apiBase.replace(/\/+$/, "");
    if (url.length <= base.length || url.indexOf(base) !== 0) return null;
    var rest = url.slice(base.length);
    if (rest.charAt(0) !== "/") return null;
    var queryAt = rest.search(/[?#]/);
    return queryAt === -1 ? rest : rest.slice(0, queryAt);
  }

  /**
   * True for anything under the API's auth namespace. Checked before every
   * other rule and independently of the allowlist, so no future entry can
   * accidentally widen into it.
   */
  function isAuthUrl(url, apiBase) {
    var path = apiPath(url, apiBase);
    if (path === null) {
      // Without a published API base, fall back to the shape the production
      // rewrite produces (`/api/auth/...`) so auth is still never cached.
      var parsed = safeUrl(url);
      if (parsed === null) return false;
      return /^\/api\/auth(\/|$)/.test(parsed.pathname);
    }
    return path === "/auth" || path.indexOf("/auth/") === 0;
  }

  function isSwrAllowedPath(path) {
    if (!isNonEmptyString(path)) return false;
    for (var i = 0; i < SWR_ALLOWLIST.length; i += 1) {
      var entry = SWR_ALLOWLIST[i];
      if (path === entry || path.indexOf(entry + "/") === 0) return true;
    }
    return false;
  }

  function isImmutableAssetPath(path) {
    if (!isNonEmptyString(path)) return false;
    for (var i = 0; i < IMMUTABLE_PREFIXES.length; i += 1) {
      if (path.indexOf(IMMUTABLE_PREFIXES[i]) === 0) return true;
    }
    return false;
  }

  function isInternalKey(path) {
    return isNonEmptyString(path) && path.indexOf(INTERNAL_PREFIX) === 0;
  }

  /**
   * Which strategy answers a request.
   *
   *   "bypass"            hands the request straight to the network, untouched.
   *   "navigation"        network first, cached document, then the offline page.
   *   "static"            cache first; content-hashed URLs cannot go stale.
   *   "api-swr"           cached copy now, refreshed in the background.
   *   "saved-first"       a saved page image: cache first, network only on miss.
   *   "network-then-saved" network first, falling back to a saved copy offline.
   *
   * `input` is plain data so this is testable without a Request:
   * `{ method, url, mode, destination, hasRange, origin, apiBase }`.
   */
  function classifyRequest(input) {
    var request = input || {};
    // Rule 1: only GET is ever cached, and a request we will not cache is a
    // request we must not answer from a cache either.
    if (request.method !== "GET") return "bypass";

    var url = safeUrl(request.url);
    if (url === null) return "bypass";
    if (url.protocol !== "http:" && url.protocol !== "https:") return "bypass";

    // Rule 2: auth, always, before anything else.
    if (isAuthUrl(request.url, request.apiBase)) return "bypass";

    // A 206 cannot be stored, so a ranged request is never intercepted.
    if (request.hasRange === true) return "bypass";

    var sameOrigin = url.origin === request.origin;
    if (sameOrigin && isInternalKey(url.pathname)) return "bypass";

    if (request.mode === "navigate") {
      return sameOrigin ? "navigation" : "bypass";
    }

    if (sameOrigin && isImmutableAssetPath(url.pathname)) return "static";

    var path = apiPath(request.url, request.apiBase);
    if (path !== null) {
      if (isSwrAllowedPath(path)) return "api-swr";
      // A page image is the one thing worth answering from the cache without
      // asking the network first: it is immutable for the life of the page id,
      // it is what "saved for offline" bought, and a reader on a train should
      // not wait for a timeout per page.
      if (request.destination === "image") return "saved-first";
      return "network-then-saved";
    }

    return "bypass";
  }

  /** A response worth storing: a real, complete, same-origin-readable 200. */
  function isCacheableResponse(response) {
    if (!response) return false;
    if (response.status !== 200) return false;
    if (response.redirected === true) return false;
    // An opaque cross-origin response has an unreadable status, so storing one
    // means caching a failure and serving it back forever.
    if (response.type === "opaque" || response.type === "opaqueredirect") return false;
    return true;
  }

  /** Bytes a stored response occupies, from its own headers when it says. */
  function responseSize(headers) {
    if (!headers) return 0;
    var raw = typeof headers.get === "function" ? headers.get("content-length") : null;
    var parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }

  // --- Saved chapters: retention, eviction, pressure ------------------------

  function entryList(index) {
    var entries = index && index.entries ? index.entries : {};
    var out = [];
    for (var key in entries) {
      if (Object.prototype.hasOwnProperty.call(entries, key)) out.push(entries[key]);
    }
    return out;
  }

  /**
   * Saved chapters whose 2-day timer has run out.
   *
   * The trigger is `readAt` — stamped when a chapter is FINISHED, cleared when
   * it is reopened, so a re-read cancels its own deletion instead of vanishing
   * mid-scroll. The chapter currently on screen is never returned, expired or
   * not. Retention of `null` (or <= 0) means "never expire", which is how the
   * rule is turned off without a rebuild.
   */
  function selectExpiredKeys(index, now, options) {
    var settings = options || {};
    // An explicit null is "never expire" and must not fall through to the
    // default — that is the difference between honouring "off" and ignoring it.
    var retention =
      settings.retentionMs === undefined ? DEFAULT_RETENTION_MS : settings.retentionMs;
    var protectKey = settings.protectKey || null;
    var out = [];
    if (!(retention > 0)) return out;
    var entries = entryList(index);
    for (var i = 0; i < entries.length; i += 1) {
      var entry = entries[i];
      if (!entry || entry.key === protectKey) continue;
      if (typeof entry.readAt !== "number" || !(entry.readAt > 0)) continue;
      if (now - entry.readAt >= retention) out.push(entry.key);
    }
    return out;
  }

  /**
   * Chapters that pressure eviction may take, oldest finished first.
   *
   * Only FINISHED chapters are candidates. An unread chapter is never deleted
   * to make room — the queue stalls at the floor instead, because silently
   * deleting something the user has not read yet is worse than telling them
   * storage is full. The open chapter is excluded whatever its state.
   */
  function selectEvictionCandidates(index, options) {
    var settings = options || {};
    var protectKey = settings.protectKey || null;
    var candidates = [];
    var entries = entryList(index);
    for (var i = 0; i < entries.length; i += 1) {
      var entry = entries[i];
      if (!entry || entry.key === protectKey) continue;
      if (typeof entry.readAt !== "number" || !(entry.readAt > 0)) continue;
      candidates.push(entry);
    }
    candidates.sort(function compare(a, b) {
      return a.readAt - b.readAt;
    });
    return candidates.map(function toKey(entry) {
      return entry.key;
    });
  }

  /**
   * Is the origin close enough to its quota that saving more should stop?
   * `estimate` is a `navigator.storage.estimate()` result; an unusable one
   * reports no pressure, because refusing to save on a browser that will not
   * say is worse than trying and failing on quota.
   */
  function storagePressure(estimate, options) {
    var settings = options || {};
    var reserve =
      typeof settings.reserveBytes === "number" ? settings.reserveBytes : STORAGE_RESERVE_BYTES;
    var maxRatio =
      typeof settings.maxUsageRatio === "number" ? settings.maxUsageRatio : MAX_USAGE_RATIO;
    var incoming = typeof settings.incomingBytes === "number" ? settings.incomingBytes : 0;

    if (!estimate || !Number.isFinite(estimate.quota) || !Number.isFinite(estimate.usage)) {
      return { known: false, underPressure: false, usage: 0, quota: 0, free: 0, ratio: 0 };
    }
    var usage = Math.max(0, estimate.usage) + Math.max(0, incoming);
    var quota = Math.max(0, estimate.quota);
    var free = Math.max(0, quota - usage);
    var ratio = quota > 0 ? usage / quota : 0;
    return {
      known: true,
      underPressure: quota > 0 && (free < reserve || ratio > maxRatio),
      usage: usage,
      quota: quota,
      free: free,
      ratio: ratio,
    };
  }

  global.MMOfflinePolicy = {
    RUNTIME_VERSION: RUNTIME_VERSION,
    CONTENT_VERSION: CONTENT_VERSION,
    PREFIX: PREFIX,
    INTERNAL_PREFIX: INTERNAL_PREFIX,
    INDEX_KEY: INDEX_KEY,
    STATE_KEY: STATE_KEY,
    DEFAULT_RETENTION_MS: DEFAULT_RETENTION_MS,
    STORAGE_RESERVE_BYTES: STORAGE_RESERVE_BYTES,
    MAX_USAGE_RATIO: MAX_USAGE_RATIO,
    SWR_ALLOWLIST: SWR_ALLOWLIST,
    scopeToken: scopeToken,
    shellCacheName: shellCacheName,
    staticCacheName: staticCacheName,
    pagesCacheName: pagesCacheName,
    stateCacheName: stateCacheName,
    apiCacheName: apiCacheName,
    offlineCacheName: offlineCacheName,
    parseCacheName: parseCacheName,
    isObsoleteCacheName: isObsoleteCacheName,
    selectObsoleteCaches: selectObsoleteCaches,
    selectScopeCaches: selectScopeCaches,
    apiPath: apiPath,
    isAuthUrl: isAuthUrl,
    isSwrAllowedPath: isSwrAllowedPath,
    isImmutableAssetPath: isImmutableAssetPath,
    isInternalKey: isInternalKey,
    classifyRequest: classifyRequest,
    isCacheableResponse: isCacheableResponse,
    responseSize: responseSize,
    selectExpiredKeys: selectExpiredKeys,
    selectEvictionCandidates: selectEvictionCandidates,
    storagePressure: storagePressure,
  };
})(typeof self !== "undefined" ? self : globalThis);
