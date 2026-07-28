import { readFileSync } from "node:fs";

/**
 * A service-worker environment, in Node, for `public/sw.js`.
 *
 * The unit tests cover every decision the worker makes from data alone. They
 * cannot cover the half that matters most in practice — what actually lands in
 * which cache, and what comes back out of it when the network is gone — because
 * that half only exists inside a `ServiceWorkerGlobalScope`.
 *
 * So this builds one: an in-memory Cache Storage, a scripted `fetch`, a client
 * list, and the event plumbing to dispatch install/activate/fetch/message. The
 * worker source is then executed against it unmodified. Every assertion in
 * `sw-integration.test.ts` is therefore about the file that ships, not about a
 * description of it.
 *
 * Kept out of the `*.test.ts` glob so it is a fixture rather than a suite.
 */

const POLICY_SOURCE = readFileSync(
  new URL("../../../public/sw-policy.js", import.meta.url),
  "utf8",
);
const WORKER_SOURCE = readFileSync(new URL("../../../public/sw.js", import.meta.url), "utf8");

export const ORIGIN = "https://manhwa.example";
export const API_BASE = `${ORIGIN}/api`;

interface StoredResponse {
  body: string;
  status: number;
  headers: Record<string, string>;
}

type RequestLike = string | { url: string };

function urlOf(request: RequestLike): string {
  const raw = typeof request === "string" ? request : request.url;
  return new URL(raw, ORIGIN).toString();
}

function stripSearch(url: string): string {
  const parsed = new URL(url);
  parsed.search = "";
  return parsed.toString();
}

interface MatchOptions {
  ignoreSearch?: boolean;
}

type Fetcher = (request: RequestLike) => Promise<Response>;

class FakeCache {
  readonly entries = new Map<string, StoredResponse>();

  constructor(private readonly fetcher: Fetcher) {}

  async match(request: RequestLike, options?: MatchOptions): Promise<Response | undefined> {
    const key = urlOf(request);
    let stored = this.entries.get(key);
    if (!stored && options?.ignoreSearch) {
      const bare = stripSearch(key);
      for (const [candidate, value] of this.entries) {
        if (stripSearch(candidate) === bare) {
          stored = value;
          break;
        }
      }
    }
    if (!stored) return undefined;
    return new Response(stored.body, { status: stored.status, headers: stored.headers });
  }

  async put(request: RequestLike, response: Response): Promise<void> {
    // Stored as text, so a cached entry can be handed out many times without
    // the body-already-consumed problem a real Response would have.
    const headers: Record<string, string> = {};
    response.headers.forEach((value, key) => {
      headers[key] = value;
    });
    this.entries.set(urlOf(request), {
      body: await response.text(),
      status: response.status,
      headers,
    });
  }

  /** `cache.add` fetches then stores, and rejects on a non-2xx like the real one. */
  async add(request: RequestLike): Promise<void> {
    const response = await this.fetcher(request);
    if (!response.ok) throw new TypeError("Request failed");
    await this.put(request, response);
  }

  async delete(request: RequestLike): Promise<boolean> {
    return this.entries.delete(urlOf(request));
  }

  async keys(): Promise<{ url: string }[]> {
    return [...this.entries.keys()].map((url) => ({ url }));
  }
}

class FakeCacheStorage {
  readonly caches = new Map<string, FakeCache>();

  constructor(private readonly fetcher: Fetcher) {}

  async open(name: string): Promise<FakeCache> {
    const existing = this.caches.get(name);
    if (existing) return existing;
    const created = new FakeCache(this.fetcher);
    this.caches.set(name, created);
    return created;
  }

  async has(name: string): Promise<boolean> {
    return this.caches.has(name);
  }

  async keys(): Promise<string[]> {
    return [...this.caches.keys()];
  }

  async delete(name: string): Promise<boolean> {
    return this.caches.delete(name);
  }
}

export interface RouteResult {
  status?: number;
  body?: string;
  headers?: Record<string, string>;
}

export interface HarnessClient {
  id: string;
  messages: unknown[];
}

export interface Harness {
  self: Record<string, unknown>;
  storage: FakeCacheStorage;
  /** Canned responses by absolute URL. */
  routes: Map<string, RouteResult>;
  /** Every URL the worker asked the network for, in order. */
  fetched: string[];
  offline: boolean;
  estimate: { usage: number; quota: number } | null;
  clients: HarnessClient[];
  cacheNames(): Promise<string[]>;
  cacheFor(name: string): FakeCache | undefined;
  dispatchInstall(): Promise<void>;
  dispatchActivate(): Promise<void>;
  dispatchMessage(data: unknown, clientId?: string): Promise<{ ok: boolean } & Record<string, unknown>>;
  dispatchFetch(input: FetchInput): Promise<FetchOutcome>;
}

export interface FetchInput {
  url: string;
  method?: string;
  mode?: string;
  destination?: string;
  clientId?: string;
  headers?: Record<string, string>;
}

export interface FetchOutcome {
  /** False when the worker declined to handle the request at all. */
  handled: boolean;
  response: Response | null;
  error: unknown;
}

export function createHarness(): Harness {
  const routes = new Map<string, RouteResult>();
  const fetched: string[] = [];
  const listeners = new Map<string, (event: unknown) => void>();
  const storage = new FakeCacheStorage((request) => fakeFetch(request));

  const harness: Partial<Harness> & { offline: boolean } = {
    offline: false,
    estimate: { usage: 1_000, quota: 10_000_000_000 },
    clients: [{ id: "client-a", messages: [] }],
  };

  async function fakeFetch(request: RequestLike): Promise<Response> {
    const url = urlOf(request);
    fetched.push(url);
    if (harness.offline) throw new TypeError("Failed to fetch");
    const route = routes.get(url);
    if (!route) return new Response("not found", { status: 404 });
    const headers = {
      "content-length": String((route.body ?? "").length),
      ...(route.headers ?? {}),
    };
    return new Response(route.body ?? "", { status: route.status ?? 200, headers });
  }

  const workerSelf: Record<string, unknown> = {
    location: { origin: ORIGIN },
    navigator: {
      storage: {
        estimate: async () => harness.estimate,
      },
    },
    registration: { scope: `${ORIGIN}/` },
    skipWaiting: () => {},
    addEventListener: (type: string, handler: (event: unknown) => void) => {
      listeners.set(type, handler);
    },
    clients: {
      claim: async () => {},
      matchAll: async () =>
        (harness.clients ?? []).map((client) => ({
          id: client.id,
          postMessage: (message: unknown) => client.messages.push(message),
        })),
    },
  };

  const importScripts = () => {
    new Function("self", POLICY_SOURCE)(workerSelf);
  };

  // Node's global Request rejects a relative URL; inside a worker one resolves
  // against the worker's scope, which is what `sw.js` relies on when it
  // precaches "/offline-fallback.html".
  class ScopedRequest {
    readonly url: string;
    readonly method: string;
    readonly headers: Headers;
    constructor(input: RequestLike, init?: { method?: string; headers?: HeadersInit }) {
      this.url = urlOf(input);
      this.method = init?.method ?? "GET";
      this.headers = new Headers(init?.headers ?? {});
    }
  }

  new Function(
    "self",
    "importScripts",
    "caches",
    "fetch",
    "Request",
    WORKER_SOURCE,
  )(workerSelf, importScripts, storage, fakeFetch, ScopedRequest);

  async function dispatch(type: string, event: Record<string, unknown>): Promise<void> {
    const handler = listeners.get(type);
    if (!handler) throw new Error(`no ${type} listener registered`);
    const pending: Promise<unknown>[] = [];
    handler({ ...event, waitUntil: (promise: Promise<unknown>) => pending.push(promise) });
    await Promise.all(pending);
  }

  const api: Harness = {
    self: workerSelf,
    storage,
    routes,
    fetched,
    get offline() {
      return harness.offline;
    },
    set offline(value: boolean) {
      harness.offline = value;
    },
    get estimate() {
      return harness.estimate ?? null;
    },
    set estimate(value: { usage: number; quota: number } | null) {
      harness.estimate = value;
    },
    clients: harness.clients as HarnessClient[],

    cacheNames: () => storage.keys(),
    cacheFor: (name: string) => storage.caches.get(name),

    dispatchInstall: () => dispatch("install", {}),
    dispatchActivate: () => dispatch("activate", {}),

    async dispatchMessage(data: unknown, clientId = "client-a") {
      let reply: Record<string, unknown> = { ok: false, reason: "no-reply" };
      const pending: Promise<unknown>[] = [];
      const handler = listeners.get("message");
      if (!handler) throw new Error("no message listener registered");
      handler({
        data,
        source: { id: clientId },
        ports: [
          {
            postMessage: (value: unknown) => {
              reply = value as Record<string, unknown>;
            },
          },
        ],
        waitUntil: (promise: Promise<unknown>) => pending.push(promise),
      });
      await Promise.all(pending);
      return reply as { ok: boolean } & Record<string, unknown>;
    },

    async dispatchFetch(input: FetchInput) {
      const handler = listeners.get("fetch");
      if (!handler) throw new Error("no fetch listener registered");
      const headers = new Headers(input.headers ?? {});
      const request = {
        url: new URL(input.url, ORIGIN).toString(),
        method: input.method ?? "GET",
        mode: input.mode ?? "cors",
        destination: input.destination ?? "",
        headers,
      };
      let handled = false;
      let promise: Promise<Response> | null = null;
      const pending: Promise<unknown>[] = [];
      handler({
        request,
        clientId: input.clientId ?? "client-a",
        respondWith: (value: Promise<Response>) => {
          handled = true;
          promise = value;
        },
        waitUntil: (value: Promise<unknown>) => pending.push(value),
      });
      let response: Response | null = null;
      let error: unknown = null;
      if (promise) {
        try {
          response = await (promise as Promise<Response>);
        } catch (caught) {
          error = caught;
        }
      }
      await Promise.allSettled(pending);
      return { handled, response, error };
    },
  };

  return api;
}

/** Register a canned network response. */
export function route(harness: Harness, url: string, result: RouteResult = {}): void {
  harness.routes.set(new URL(url, ORIGIN).toString(), result);
}

/** Read the worker's saved-chapter index straight out of its cache. */
export async function readIndex(
  harness: Harness,
  cacheName: string,
): Promise<{ retentionMs: number | null; entries: Record<string, IndexEntry> } | null> {
  const cache = harness.cacheFor(cacheName);
  if (!cache) return null;
  const hit = await cache.match(`${ORIGIN}/__mm-offline/index.json`);
  if (!hit) return null;
  return hit.json();
}

export interface IndexEntry {
  key: string;
  savedPages: number;
  pageCount: number;
  bytes: number;
  status: string;
  failed: number;
  stale: boolean;
  readAt: number | null;
  urls: string[];
}
