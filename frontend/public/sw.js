/*
 * ManhwaManiacs service worker.
 *
 * Two jobs:
 *   1. Keep the app usable when the network is not. Documents, immutable build
 *      assets and a small allowlist of harmless API GETs are cached with a
 *      strategy chosen per request by `sw-policy.js`.
 *   2. Store whole chapters on purpose, per (user, profile), so they can be
 *      read with the server unreachable — the thing docs/OFFLINE_READING.md
 *      needs five to six weeks of native iOS work to achieve, and which a
 *      Cache API and a fetch handler give the web for free.
 *
 * Every decision that can be made from data alone lives in `sw-policy.js` and
 * is unit-tested; this file is the part that has to touch the network, Cache
 * Storage and clients.
 *
 * UPDATE STORY. A stale app shell that cannot be replaced is the worst thing a
 * service worker can do to a site, so:
 *   - install NEVER calls skipWaiting on its own. A new worker waits, the page
 *     is told, and the user chooses when to reload. Swapping the bundle under
 *     someone mid-chapter is not an improvement.
 *   - the page can ask for the swap ("mm-offline/skip-waiting"), and reloads
 *     itself once on `controllerchange`.
 *   - navigations are network-FIRST, so an online reader always gets the HTML
 *     the server just built; a cached document can only ever be served when the
 *     network actually failed.
 *   - activate deletes every cache of a superseded runtime generation, so
 *     bumping RUNTIME_VERSION in sw-policy.js is a full reset of the caching
 *     behaviour without touching saved chapters (they are versioned separately
 *     by CONTENT_VERSION).
 *   - "Reset offline data" in the app unregisters and clears everything, which
 *     is the manual escape hatch if all of the above somehow fails.
 *
 * SW_BUILD is part of the policy import URL: bumping it changes the bytes of
 * this file (so the browser sees an update) AND the URL of the imported policy
 * (so the update cannot be served an old policy from the HTTP cache).
 */

var SW_BUILD = "2026-09-03.1";

importScripts("/sw-policy.js?v=" + SW_BUILD);

var policy = self.MMOfflinePolicy;

var OFFLINE_URL = "/offline-fallback.html";

/** Precached at install: enough to render *something* with no network at all. */
var SHELL_ASSETS = [
  OFFLINE_URL,
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/manifest.webmanifest",
];

/**
 * Documents warmed on activate, so a cold launch with no network has something
 * to render even if the user never visited them in this session.
 *
 * `/library` is the manifest's start_url — what an installed icon opens.
 * `/downloads` is the only action the offline fallback page offers ("Saved
 * chapters"), so without it here that link fails to the very page it was
 * clicked from. Both are client-rendered shells that fetch their data over the
 * API, which is what makes them safe to share across profiles: the per-profile
 * content arrives separately, out of a per-profile cache.
 */
var WARM_DOCUMENTS = ["/library", "/downloads"];

/** Parallel image fetches per save. Enough to saturate a NAS, not to drown it. */
var SAVE_CONCURRENCY = 4;

/** How often, in images, a save re-checks that there is still room. */
var PRESSURE_CHECK_EVERY = 5;

/** Progress broadcasts are throttled: a 200-page chapter is not 200 renders. */
var PROGRESS_THROTTLE_MS = 300;

/**
 * Caps on the two caches that would otherwise grow forever.
 *
 * Documents: one entry per URL ever visited, and a library has a page per
 * series. Build assets: every deploy publishes a new set of content-hashed
 * chunks and the old ones are never requested again, so without a cap the
 * static cache would accumulate one full bundle per release — an unbounded
 * cost the reader never asked for and cannot see.
 *
 * Trimming is safe precisely because these are caches: both strategies fall
 * back to the network, so evicting something still in use costs one request.
 * Saved chapters are NOT capped here — those are the bytes the user asked to
 * keep, and they are governed by retention and eviction instead.
 */
var MAX_PAGE_ENTRIES = 60;
var MAX_STATIC_ENTRIES = 240;

// --- Worker state ----------------------------------------------------------

/**
 * `{ scope, apiBase }` last published by any client, persisted so a restarted
 * worker can still answer from the right profile's cache before any page has
 * had a chance to talk to it.
 */
var persistedState = null;
var persistedStateLoaded = false;

/**
 * Per-client scope. A fetch event names the client that made it, so a request
 * is answered from the cache of the profile *that tab* is signed into, not
 * whichever tab published last.
 */
var clientScopes = new Map();

/** Chapter key currently open in a reader, which eviction must never take. */
var openChapterKey = null;

/** Keys whose save is running, so a second request does not start it twice. */
var activeSaves = new Map();

/** Serialises index writes: the worker is the only writer, one write at a time. */
var indexQueue = Promise.resolve();

// --- Small helpers ---------------------------------------------------------

function noop() {}

function stateCache() {
  return caches.open(policy.stateCacheName());
}

function jsonResponse(value) {
  return new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
}

async function readJson(cache, key) {
  var hit = await cache.match(key, { ignoreVary: true });
  if (!hit) return null;
  try {
    return await hit.json();
  } catch {
    return null;
  }
}

async function loadPersistedState() {
  if (persistedStateLoaded) return persistedState;
  var cache = await stateCache();
  persistedState = await readJson(cache, policy.STATE_KEY);
  persistedStateLoaded = true;
  return persistedState;
}

async function savePersistedState(next) {
  persistedState = next;
  persistedStateLoaded = true;
  var cache = await stateCache();
  await cache.put(policy.STATE_KEY, jsonResponse(next));
}

/**
 * The (scope, apiBase) a request belongs to. Prefers the tab that made it and
 * falls back to the last published state — never to a default scope, because
 * "no scope" has to mean "no saved chapters", not "somebody's saved chapters".
 */
async function resolveContext(clientId) {
  if (clientId && clientScopes.has(clientId)) return clientScopes.get(clientId);
  var stored = await loadPersistedState();
  return stored || { scope: null, apiBase: null };
}

// --- Install / activate ----------------------------------------------------

self.addEventListener("install", function onInstall(event) {
  event.waitUntil(
    caches.open(policy.shellCacheName()).then(function fill(cache) {
      // Individually, not addAll: one missing icon must not fail the install
      // and leave the site with no worker at all.
      return Promise.all(
        SHELL_ASSETS.map(function add(url) {
          return cache.add(new Request(url, { cache: "reload" })).catch(noop);
        }),
      );
    }),
  );
  // No skipWaiting here on purpose — see the update story at the top.
});

self.addEventListener("activate", function onActivate(event) {
  event.waitUntil(
    (async function activate() {
      var names = await caches.keys();
      await Promise.all(
        policy.selectObsoleteCaches(names).map(function drop(name) {
          return caches.delete(name);
        }),
      );
      await self.clients.claim();
      await warmDocuments();
      await broadcastState();
    })(),
  );
});

/** Best-effort: put the launch documents in the document cache. */
async function warmDocuments() {
  var cache = await caches.open(policy.pagesCacheName());
  for (var i = 0; i < WARM_DOCUMENTS.length; i += 1) {
    var url = WARM_DOCUMENTS[i];
    try {
      var response = await fetch(url, { credentials: "include" });
      if (policy.isCacheableResponse(response)) {
        await cache.put(url, response);
      }
    } catch {
      // Offline at activate time is normal, and one failure must not stop the
      // rest; the first successful navigation fills these in anyway.
    }
  }
}

// --- Fetch -----------------------------------------------------------------

self.addEventListener("fetch", function onFetch(event) {
  var request = event.request;

  // Anything that can never be cached is left completely alone — not even
  // re-issued through the worker — so a bug in here cannot break a POST, a
  // ranged read or an extension.
  if (!interceptable(request)) return;

  // Fast path. Recognising an API URL needs the API base, which arrives from
  // the page; once it is in memory the whole decision is synchronous and the
  // worker stays out of the way of every request that is not its business.
  if (persistedStateLoaded) {
    var context = clientScopes.get(event.clientId) ||
      persistedState || { scope: null, apiBase: null };
    var strategy = classify(request, context.apiBase);
    if (strategy === "bypass") return;
    event.respondWith(dispatch(event, request, strategy, context));
    return;
  }

  event.respondWith(handleFetch(event, request));
});

/** Requests the worker is allowed to look at at all. */
function interceptable(request) {
  if (request.method !== "GET") return false;
  if (request.headers.has("range")) return false;
  return request.url.indexOf("http:") === 0 || request.url.indexOf("https:") === 0;
}

function classify(request, apiBase) {
  return policy.classifyRequest({
    method: request.method,
    url: request.url,
    mode: request.mode,
    destination: request.destination,
    hasRange: request.headers.has("range"),
    origin: self.location.origin,
    apiBase: apiBase,
  });
}

async function handleFetch(event, request) {
  var context = await resolveContext(event.clientId);
  return dispatch(event, request, classify(request, context.apiBase), context);
}

function dispatch(event, request, strategy, context) {
  switch (strategy) {
    case "navigation":
      return handleNavigation(event, request, context);
    case "static":
      return handleStatic(request);
    case "api-swr":
      return handleApiSwr(event, request, context);
    case "saved-first":
      return handleSavedFirst(request, context);
    case "network-then-saved":
      return handleNetworkThenSaved(event, request, context);
    default:
      return fetch(request);
  }
}

/**
 * Network first. The live server is always right about the app shell; the cache
 * is only ever consulted when the network has actually failed, which is what
 * stops a stale build stranding anybody.
 */
async function handleNavigation(event, request, context) {
  try {
    var response = await fetch(request);
    if (policy.isCacheableResponse(response)) {
      var copy = response.clone();
      event.waitUntil(
        caches.open(policy.pagesCacheName()).then(function store(cache) {
          return cache.put(request, copy).then(function trim() {
            return trimCache(cache, MAX_PAGE_ENTRIES);
          });
        }),
      );
    }
    return response;
  } catch {
    var cache = await caches.open(policy.pagesCacheName());
    var hit =
      (await cache.match(request, { ignoreVary: true })) ||
      // `/reader/12/34?page=7` is the same document as `/reader/12/34`.
      (await cache.match(request, { ignoreVary: true, ignoreSearch: true }));
    if (hit) return hit;

    // Then the documents saved alongside a chapter, in THIS client's scope.
    //
    // The document cache only holds URLs the browser actually navigated to, and
    // inside the app nobody navigates: clicking a chapter is a client-side
    // route change, so /reader/{series}/{chapter} is never requested as a
    // document and never lands there. A cold launch from the home screen, or a
    // reload with no signal, is a real navigation — and without this it would
    // hit the offline page while the chapter sat in the cache, fully saved.
    // That is why `saveChapter` fetches `documentUrl` in the first place.
    //
    // Scoped, like every other read of that cache: `matchSaved` resolves the
    // cache name from the scope this tab published, so it can only ever return
    // a document the looking profile saved for itself.
    var saved = await matchSaved(request, (context || {}).scope, true);
    if (saved) return saved;

    var shell = await caches.open(policy.shellCacheName());
    var fallback = await shell.match(OFFLINE_URL, { ignoreVary: true });
    if (fallback) return fallback;
    return new Response("You are offline.", {
      status: 503,
      headers: { "Content-Type": "text/plain" },
    });
  }
}

/** Cache first: these URLs are content-hashed, so a hit cannot be stale. */
async function handleStatic(request) {
  var cache = await caches.open(policy.staticCacheName());
  var hit = await cache.match(request, { ignoreVary: true });
  if (hit) return hit;
  var response = await fetch(request);
  if (policy.isCacheableResponse(response)) {
    await cache.put(request, response.clone());
    await trimCache(cache, MAX_STATIC_ENTRIES);
  }
  return response;
}

/**
 * Drop the oldest entries until `cache` holds at most `max`.
 *
 * `keys()` is in insertion order and a re-`put` moves an entry to the end, so
 * the front of the list is the least recently stored — close enough to least
 * recently used for a cache whose miss costs one request.
 */
async function trimCache(cache, max) {
  var keys = await cache.keys();
  for (var i = 0; i < keys.length - max; i += 1) {
    await cache.delete(keys[i]);
  }
}

/**
 * Stale-while-revalidate, on the short allowlist in sw-policy.js only, in a
 * cache named for the active profile. Without a scope nothing is stored and
 * nothing is served: an unscoped cache would be exactly the leak this app has
 * spent the day removing from localStorage.
 */
async function handleApiSwr(event, request, context) {
  var cacheName = policy.apiCacheName(context.scope);
  if (cacheName === null) return fetch(request);

  var cache = await caches.open(cacheName);
  var hit = await cache.match(request, { ignoreVary: true });

  var revalidate = fetch(request)
    .then(function store(response) {
      if (policy.isCacheableResponse(response)) {
        return cache.put(request, response.clone()).then(function pass() {
          return response;
        });
      }
      return response;
    })
    .catch(function offline() {
      return null;
    });

  if (hit) {
    event.waitUntil(revalidate);
    return hit;
  }
  var fresh = await revalidate;
  return fresh || Response.error();
}

/** A saved page image: the whole point of saving is not asking the network. */
async function handleSavedFirst(request, context) {
  var hit = await matchSaved(request, context.scope);
  if (hit) return hit;
  return fetch(request);
}

/**
 * Live data when there is a network, the saved copy when there is not. Used for
 * the chapter payload: page ids move on rescan, so the server's answer wins
 * whenever there is one, and the saved copy is checked for drift as it does.
 */
async function handleNetworkThenSaved(event, request, context) {
  try {
    var response = await fetch(request);
    if (policy.isCacheableResponse(response)) {
      event.waitUntil(refreshSavedPayload(request, response.clone(), context.scope));
    }
    return response;
  } catch {
    var hit = await matchSaved(request, context.scope);
    return hit || Response.error();
  }
}

/**
 * Look a request up in the saved-chapter cache of `scope`, or null when there
 * is no scope — never a shared fallback.
 *
 * `ignoreSearch` is opt-in and used only for documents. It must stay off
 * everywhere else: the chapter manifest is keyed by its
 * `?source=&series=&chapter=` query, so ignoring the query string would answer
 * one saved chapter's manifest with another's.
 */
async function matchSaved(request, scope, ignoreSearch) {
  var cacheName = policy.offlineCacheName(scope);
  if (cacheName === null) return null;
  if (!(await caches.has(cacheName))) return null;
  var cache = await caches.open(cacheName);
  var hit = await cache.match(request, { ignoreVary: true });
  if (hit || ignoreSearch !== true) return hit;
  return cache.match(request, { ignoreVary: true, ignoreSearch: true });
}

/**
 * Keep a saved chapter's manifest in step with the source, and flag it when the
 * pages moved underneath it.
 *
 * A source's page URLs are not stable when it re-lists a chapter, and every
 * saved image is keyed by its URL. If the URLs change, the saved images are
 * orphans and the chapter would fail to open offline with no explanation, so
 * the entry is marked stale and the UI offers to save it again.
 */
async function refreshSavedPayload(request, response, scope) {
  var cacheName = policy.offlineCacheName(scope);
  if (cacheName === null) return;
  var index = await readIndex(scope);
  var entry = findEntryByPayloadUrl(index, request.url);
  if (!entry) return;

  var cache = await caches.open(cacheName);
  var body = await response.text();
  var previous = await cache.match(request.url, { ignoreVary: true });
  var previousIds = previous ? pageIdsOf(await previous.text()) : null;
  var nextIds = pageIdsOf(body);

  await cache.put(
    request.url,
    new Response(body, { headers: { "Content-Type": "application/json" } }),
  );

  var drifted =
    previousIds !== null && nextIds !== null && previousIds.join(",") !== nextIds.join(",");
  if (drifted) {
    await mutateIndex(scope, function markStale(draft) {
      var current = draft.entries[entry.key];
      if (current) current.stale = true;
      return draft;
    });
    await broadcastState();
  }
}

function pageIdsOf(bodyText) {
  try {
    var payload = JSON.parse(bodyText);
    if (!payload || !Array.isArray(payload.pages)) return null;
    return payload.pages.map(function signature(page) {
      // Page identity in a source-native manifest is (number, url): the number
      // orders the strip, the url is what a saved image is keyed by. Either one
      // moving orphans the saved bytes.
      return String(page && page.number) + " " + String(page && page.url);
    });
  } catch {
    return null;
  }
}

function findEntryByPayloadUrl(index, url) {
  var entries = index.entries;
  for (var key in entries) {
    if (Object.prototype.hasOwnProperty.call(entries, key) && entries[key].payloadUrl === url) {
      return entries[key];
    }
  }
  return null;
}

// --- The saved-chapter index ----------------------------------------------

function emptyIndex() {
  return { version: 1, retentionMs: policy.DEFAULT_RETENTION_MS, entries: {} };
}

async function readIndex(scope) {
  var cacheName = policy.offlineCacheName(scope);
  if (cacheName === null) return emptyIndex();
  if (!(await caches.has(cacheName))) return emptyIndex();
  var cache = await caches.open(cacheName);
  var stored = await readJson(cache, policy.INDEX_KEY);
  if (!stored || typeof stored !== "object" || !stored.entries) return emptyIndex();
  if (stored.retentionMs === undefined) stored.retentionMs = policy.DEFAULT_RETENTION_MS;
  return stored;
}

/**
 * Read-modify-write the index, serialised. The worker is the only writer — the
 * page only ever reads through it — so there is no lost update to reconcile.
 */
function mutateIndex(scope, mutator) {
  var run = indexQueue.then(async function apply() {
    var cacheName = policy.offlineCacheName(scope);
    if (cacheName === null) return emptyIndex();
    var index = await readIndex(scope);
    var next = mutator(index) || index;
    var cache = await caches.open(cacheName);
    await cache.put(policy.INDEX_KEY, jsonResponse(next));
    return next;
  });
  // Keep the chain alive even if one mutation throws.
  indexQueue = run.catch(noop);
  return run;
}

// --- Saving ----------------------------------------------------------------

/**
 * Fetch and store one chapter: its manifest, its page images and the document
 * that renders it. Adjacency travels inside the manifest (`prev`/`next`), so
 * there is nothing extra to fetch for it.
 *
 * Runs in the worker rather than the page so navigating away — or locking the
 * phone — does not abandon a half-saved chapter, and so a resumed save can skip
 * what is already stored.
 */
async function saveChapter(payload) {
  var scope = payload.scope;
  var cacheName = policy.offlineCacheName(scope);
  if (cacheName === null) return { ok: false, reason: "no-scope" };
  if (activeSaves.has(payload.key)) return { ok: true, reason: "already-running" };

  activeSaves.set(payload.key, { cancelled: false });
  try {
    await runSave(payload, cacheName);
  } finally {
    activeSaves.delete(payload.key);
  }
  await broadcastState();
  return { ok: true };
}

async function runSave(payload, cacheName) {
  var scope = payload.scope;
  var cache = await caches.open(cacheName);
  var now = Date.now();

  var targets = [];
  if (payload.documentUrl) targets.push({ url: payload.documentUrl, kind: "document" });
  for (var e = 0; e < (payload.extraUrls || []).length; e += 1) {
    targets.push({ url: payload.extraUrls[e], kind: "api" });
  }
  for (var i = 0; i < payload.imageUrls.length; i += 1) {
    targets.push({ url: payload.imageUrls[i], kind: "image" });
  }

  await mutateIndex(scope, function upsert(draft) {
    var existing = draft.entries[payload.key];
    draft.entries[payload.key] = {
      key: payload.key,
      sourceId: payload.sourceId,
      seriesKey: payload.seriesKey,
      chapterKey: payload.chapterKey,
      title: payload.title,
      seriesTitle: payload.seriesTitle || null,
      pageCount: payload.imageUrls.length,
      payloadUrl: payload.payloadUrl,
      urls: targets.map(function url(target) {
        return target.url;
      }),
      savedPages: 0,
      bytes: 0,
      status: "saving",
      failed: 0,
      stale: false,
      savedAt: existing ? existing.savedAt : now,
      lastOpenedAt: existing ? existing.lastOpenedAt : null,
      // A save is a fresh intent to read it, so any pending expiry is off.
      readAt: null,
    };
    return draft;
  });
  await broadcastState();

  // The reader payload is supplied by the page, which already has it: one
  // fewer request, and a guarantee the cached copy is exactly the payload the
  // page listed images from.
  if (payload.payloadUrl && payload.payloadJson) {
    await cache.put(
      payload.payloadUrl,
      new Response(payload.payloadJson, {
        headers: { "Content-Type": "application/json" },
      }),
    );
  }

  var cursor = 0;
  var imagesSeen = 0;
  var savedPages = 0;
  var failed = 0;
  var bytes = 0;
  var paused = false;
  var lastBroadcast = 0;

  async function worker() {
    while (true) {
      var control = activeSaves.get(payload.key);
      if (!control || control.cancelled || paused) return;
      var index = cursor;
      cursor += 1;
      if (index >= targets.length) return;
      var target = targets[index];

      if (target.kind === "image") {
        // Counted in images, not in targets: the check has to happen BEFORE the
        // first page as well as every few pages after it, and where the images
        // start in the list depends on how many supporting URLs precede them.
        var position = imagesSeen;
        imagesSeen += 1;
        if (position % PRESSURE_CHECK_EVERY === 0) {
          var relieved = await ensureRoom(scope);
          if (!relieved) {
            paused = true;
            return;
          }
        }
      }

      var existing = await cache.match(target.url, { ignoreVary: true });
      if (existing) {
        // Resuming a save that was interrupted: what is already stored counts.
        bytes += policy.responseSize(existing.headers);
        if (target.kind === "image") savedPages += 1;
      } else {
        try {
          var response = await fetch(target.url, {
            credentials: "include",
            headers: requestHeaders(payload, target),
          });
          if (policy.isCacheableResponse(response)) {
            var copy = response.clone();
            await cache.put(target.url, response);
            bytes += policy.responseSize(copy.headers);
            if (target.kind === "image") savedPages += 1;
          } else if (target.kind === "image") {
            failed += 1;
          }
        } catch {
          if (target.kind === "image") failed += 1;
        }
      }

      var stamp = Date.now();
      if (stamp - lastBroadcast > PROGRESS_THROTTLE_MS) {
        lastBroadcast = stamp;
        await publishProgress(scope, payload.key, savedPages, bytes, "saving");
      }
    }
  }

  var pool = [];
  for (var w = 0; w < Math.min(SAVE_CONCURRENCY, targets.length); w += 1) {
    pool.push(worker());
  }
  await Promise.all(pool);

  var control = activeSaves.get(payload.key);
  var cancelled = !control || control.cancelled;
  var status = cancelled
    ? "partial"
    : paused
      ? "paused"
      : failed > 0 || savedPages < payload.imageUrls.length
        ? "partial"
        : "ready";

  await publishProgress(scope, payload.key, savedPages, bytes, status, failed);
}

/**
 * `X-Profile-Id` on the JSON endpoints, exactly like `services/http.ts` sends
 * it, and on nothing else.
 *
 * Page images deliberately go without: an `<img>` cannot send a custom header,
 * so the reader has always fetched them without one and the endpoint does not
 * ask for it. Adding one here would make the saved request differ from the
 * request it is being saved for — and, cross-origin in dev, would trigger a
 * CORS preflight per page.
 */
function requestHeaders(payload, target) {
  if (target.kind !== "api") return undefined;
  if (typeof payload.profileId !== "number") return undefined;
  return { "X-Profile-Id": String(payload.profileId) };
}

async function publishProgress(scope, key, savedPages, bytes, status, failed) {
  await mutateIndex(scope, function update(draft) {
    var entry = draft.entries[key];
    if (!entry) return draft;
    entry.savedPages = savedPages;
    entry.bytes = bytes;
    entry.status = status;
    if (typeof failed === "number") entry.failed = failed;
    return draft;
  });
  await broadcastState();
}

/**
 * Make room, or report that there is none.
 *
 * Expired chapters go first (they were going anyway), then the oldest finished
 * ones. An unread chapter is never taken: the owner's rule is that the queue
 * stalls at the floor rather than deleting something nobody has read yet.
 */
async function ensureRoom(scope) {
  var estimate = await storageEstimate();
  var pressure = policy.storagePressure(estimate, {});
  if (!pressure.known || !pressure.underPressure) return true;

  var index = await readIndex(scope);
  var candidates = policy
    .selectExpiredKeys(index, Date.now(), {
      retentionMs: index.retentionMs,
      protectKey: openChapterKey,
    })
    .concat(
      policy.selectEvictionCandidates(index, { protectKey: openChapterKey }),
    );

  var seen = new Set();
  for (var i = 0; i < candidates.length; i += 1) {
    var key = candidates[i];
    if (seen.has(key)) continue;
    seen.add(key);
    await removeChapter(scope, key);
    var next = policy.storagePressure(await storageEstimate(), {});
    if (!next.underPressure) return true;
  }
  return false;
}

async function storageEstimate() {
  if (!self.navigator || !self.navigator.storage || !self.navigator.storage.estimate) {
    return null;
  }
  try {
    return await self.navigator.storage.estimate();
  } catch {
    return null;
  }
}

async function removeChapter(scope, key) {
  var cacheName = policy.offlineCacheName(scope);
  if (cacheName === null) return;
  var index = await readIndex(scope);
  var entry = index.entries[key];
  if (!entry) return;

  var control = activeSaves.get(key);
  if (control) control.cancelled = true;

  var cache = await caches.open(cacheName);
  var urls = (entry.urls || []).concat(entry.payloadUrl ? [entry.payloadUrl] : []);
  for (var i = 0; i < urls.length; i += 1) {
    await cache.delete(urls[i], { ignoreVary: true });
  }
  await mutateIndex(scope, function drop(draft) {
    delete draft.entries[key];
    return draft;
  });
}

/**
 * The launch/resume sweep. Runs when the app opens or comes back to the
 * foreground, never on a timer: "48 hours later" honestly means "the first time
 * you open the app after 48 hours", the same promise the native design makes.
 */
async function sweep(scope, protectKey) {
  var index = await readIndex(scope);
  var expired = policy.selectExpiredKeys(index, Date.now(), {
    retentionMs: index.retentionMs,
    protectKey: protectKey || openChapterKey,
  });
  for (var i = 0; i < expired.length; i += 1) {
    await removeChapter(scope, expired[i]);
  }
  await ensureRoom(scope);
  await broadcastState();
  return expired.length;
}

// --- Talking to the pages --------------------------------------------------

async function snapshotFor(scope) {
  var index = await readIndex(scope);
  var entries = [];
  for (var key in index.entries) {
    if (Object.prototype.hasOwnProperty.call(index.entries, key)) {
      entries.push(index.entries[key]);
    }
  }
  return {
    scopeToken: policy.scopeToken(scope),
    entries: entries,
    retentionMs: index.retentionMs,
    estimate: await storageEstimate(),
    openChapterKey: openChapterKey,
  };
}

/**
 * Push state to every client, each in ITS OWN scope. One broadcast cannot hand
 * a tab signed into profile B a list of profile A's saved chapters, because the
 * snapshot is rebuilt per client from that client's published scope.
 */
async function broadcastState() {
  var clientList = await self.clients.matchAll({ includeUncontrolled: true });
  var live = new Set();
  for (var i = 0; i < clientList.length; i += 1) {
    var client = clientList[i];
    live.add(client.id);
    var context = clientScopes.get(client.id);
    if (!context) continue;
    var snapshot = await snapshotFor(context.scope);
    client.postMessage({ type: "mm-offline/state", state: snapshot });
  }
  // Closed tabs never tell us they went; drop them here so a long-lived worker
  // does not accumulate the scope of every tab ever opened.
  clientScopes.forEach(function prune(_value, id) {
    if (!live.has(id)) clientScopes.delete(id);
  });
}

self.addEventListener("message", function onMessage(event) {
  var data = event.data;
  if (!data || typeof data.type !== "string") return;
  event.waitUntil(handleMessage(event, data));
});

async function handleMessage(event, data) {
  var reply = function respond(value) {
    if (event.ports && event.ports[0]) event.ports[0].postMessage(value);
  };

  switch (data.type) {
    case "mm-offline/skip-waiting":
      self.skipWaiting();
      reply({ ok: true });
      return;

    case "mm-offline/set-scope": {
      var context = { scope: data.scope || null, apiBase: data.apiBase || null };
      if (event.source && event.source.id) {
        clientScopes.set(event.source.id, context);
      }
      // Persisted so a restarted worker can answer image requests from the
      // right cache before any page has spoken to it.
      await savePersistedState(context);
      var snapshot = await snapshotFor(context.scope);
      reply({ ok: true, state: snapshot });
      return;
    }

    case "mm-offline/get-state": {
      var current = await resolveContext(event.source && event.source.id);
      reply({ ok: true, state: await snapshotFor(current.scope) });
      return;
    }

    case "mm-offline/save-chapter": {
      var payload = data.payload;
      if (!payload || policy.scopeToken(payload.scope) === null) {
        reply({ ok: false, reason: "no-scope" });
        return;
      }
      reply({ ok: true, accepted: true });
      await saveChapter(payload);
      return;
    }

    case "mm-offline/cancel-save": {
      var control = activeSaves.get(data.key);
      if (control) control.cancelled = true;
      reply({ ok: true });
      return;
    }

    case "mm-offline/remove-chapter": {
      await removeChapter(data.scope, data.key);
      await broadcastState();
      reply({ ok: true });
      return;
    }

    case "mm-offline/mark-opened": {
      openChapterKey = data.key;
      // Reopening cancels the expiry timer — otherwise a re-read would delete
      // itself mid-scroll.
      await mutateIndex(data.scope, function touch(draft) {
        var entry = draft.entries[data.key];
        if (entry) {
          entry.readAt = null;
          entry.lastOpenedAt = Date.now();
        }
        return draft;
      });
      await broadcastState();
      reply({ ok: true });
      return;
    }

    case "mm-offline/mark-finished": {
      await mutateIndex(data.scope, function stamp(draft) {
        var entry = draft.entries[data.key];
        if (entry) entry.readAt = Date.now();
        return draft;
      });
      await broadcastState();
      reply({ ok: true });
      return;
    }

    case "mm-offline/chapter-closed": {
      if (openChapterKey === data.key) openChapterKey = null;
      reply({ ok: true });
      return;
    }

    case "mm-offline/sweep": {
      var removed = await sweep(data.scope, data.protectKey || null);
      reply({ ok: true, removed: removed });
      return;
    }

    case "mm-offline/set-retention": {
      await mutateIndex(data.scope, function setRetention(draft) {
        draft.retentionMs =
          typeof data.retentionMs === "number" && data.retentionMs > 0
            ? data.retentionMs
            : null;
        return draft;
      });
      await sweep(data.scope, null);
      reply({ ok: true });
      return;
    }

    case "mm-offline/clear-scope": {
      var names = await caches.keys();
      var mine = policy.selectScopeCaches(names, data.scope);
      for (var i = 0; i < mine.length; i += 1) {
        await caches.delete(mine[i]);
      }
      await broadcastState();
      reply({ ok: true });
      return;
    }

    default:
      reply({ ok: false, reason: "unknown-message" });
  }
}
