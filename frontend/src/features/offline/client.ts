import { env } from "@/config/env";
import type { StorageScope } from "@/lib/scoped-storage";
import {
  OFFLINE_MESSAGE,
  isOfflineStateMessage,
  type OfflineReply,
  type SaveChapterRequest,
} from "./protocol";
import type { OfflineState, OfflineWorkerState } from "./types";

/**
 * The page half of the offline feature: register the worker, tell it which
 * profile is looking, relay requests, and hold the last state it published.
 *
 * A plain module store rather than React state because three unrelated places
 * render it — the reader's save control, the storage screen and the update
 * prompt — and they must never disagree about what is saved.
 */

const EMPTY_STATE: OfflineState = {
  readiness: "pending",
  scopeToken: null,
  entries: [],
  retentionMs: null,
  estimate: null,
  openChapterKey: null,
};

const UNSUPPORTED_STATE: OfflineState = { ...EMPTY_STATE, readiness: "unsupported" };

let snapshot: OfflineState = EMPTY_STATE;
const listeners = new Set<() => void>();

function publish(next: OfflineState): void {
  snapshot = next;
  for (const listener of listeners) listener();
}

export function getOfflineSnapshot(): OfflineState {
  return snapshot;
}

/** Stable across renders on the server, where there is no worker at all. */
export function getOfflineServerSnapshot(): OfflineState {
  return EMPTY_STATE;
}

export function subscribeOffline(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function isServiceWorkerSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in window.navigator &&
    window.isSecureContext
  );
}

/**
 * The API base as an absolute URL.
 *
 * Mirrors `resolveApiBase` in `services/http.ts:14`: production serves the
 * backend same-origin under `/api` and dev points at a separate origin. The
 * worker is told the result because a cached URL has to be recognised as an API
 * call in both shapes, and the worker cannot read `NEXT_PUBLIC_API_URL`.
 */
export function resolveApiBase(): string {
  const base = env.apiUrl;
  if (/^https?:\/\//i.test(base)) return base;
  if (typeof window !== "undefined") return `${window.location.origin}${base}`;
  return base;
}

/**
 * Whether the worker runs at all.
 *
 * Off in development unless explicitly asked for: `next dev` serves JS chunks
 * from URLs that are not content-hashed, so the cache-first rule for build
 * assets would happily serve this morning's bundle after an edit. Production
 * builds hash every chunk, which is what makes that rule safe.
 */
export function shouldRegisterWorker(): boolean {
  if (!isServiceWorkerSupported()) return false;
  if (process.env.NODE_ENV === "production") return true;
  return process.env.NEXT_PUBLIC_ENABLE_SW === "1";
}

let registrationPromise: Promise<ServiceWorkerRegistration | null> | null = null;
let messagesWired = false;

export function registerOfflineWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!shouldRegisterWorker()) {
    publish(UNSUPPORTED_STATE);
    return Promise.resolve(null);
  }
  if (registrationPromise) return registrationPromise;

  wireMessages();
  registrationPromise = window.navigator.serviceWorker
    // `updateViaCache: "none"` so neither sw.js nor the policy it imports can be
    // answered from the HTTP cache — an undetectable worker update is how a
    // stale shell becomes permanent.
    .register("/sw.js", { scope: "/", updateViaCache: "none" })
    .catch(() => {
      publish(UNSUPPORTED_STATE);
      return null;
    });
  return registrationPromise;
}

function wireMessages(): void {
  if (messagesWired || !isServiceWorkerSupported()) return;
  messagesWired = true;
  window.navigator.serviceWorker.addEventListener("message", (event: MessageEvent) => {
    if (!isOfflineStateMessage(event.data)) return;
    applyWorkerState(event.data.state);
  });
}

function applyWorkerState(state: OfflineWorkerState): void {
  publish({
    ...state,
    entries: Array.isArray(state.entries) ? state.entries : [],
    readiness: state.scopeToken === null ? "unscoped" : "ready",
  });
}

/**
 * Round-trip a message to the worker. Resolves rather than rejects on failure:
 * every caller here is best-effort, and a worker that is asleep, gone or slow
 * must degrade to "offline saving is unavailable", never to a thrown error in
 * the reader.
 */
async function ask(message: Record<string, unknown>, timeoutMs = 15_000): Promise<OfflineReply> {
  if (!isServiceWorkerSupported()) return { ok: false, reason: "unsupported" };
  let registration: ServiceWorkerRegistration | undefined;
  try {
    registration = await window.navigator.serviceWorker.ready;
  } catch {
    return { ok: false, reason: "unavailable" };
  }
  const worker = registration.active;
  if (!worker) return { ok: false, reason: "unavailable" };

  return new Promise<OfflineReply>((resolve) => {
    const channel = new MessageChannel();
    const timer = window.setTimeout(() => {
      channel.port1.close();
      resolve({ ok: false, reason: "timeout" });
    }, timeoutMs);
    channel.port1.onmessage = (event: MessageEvent) => {
      window.clearTimeout(timer);
      channel.port1.close();
      resolve((event.data as OfflineReply) ?? { ok: false, reason: "empty" });
    };
    worker.postMessage(message, [channel.port2]);
  });
}

/**
 * Tell the worker whose caches to use. Sent on mount and on every profile
 * switch; a null scope publishes "nobody", which makes the worker stop serving
 * saved content rather than fall back to the last profile's.
 */
export async function publishScope(scope: StorageScope | null): Promise<void> {
  if (!shouldRegisterWorker()) return;
  const reply = await ask({
    type: OFFLINE_MESSAGE.setScope,
    scope,
    apiBase: resolveApiBase(),
  });
  if (reply.ok && reply.state) {
    applyWorkerState(reply.state);
    return;
  }
  if (!reply.ok) publish({ ...EMPTY_STATE, readiness: "pending" });
}

export async function refreshOfflineState(): Promise<void> {
  const reply = await ask({ type: OFFLINE_MESSAGE.getState });
  if (reply.ok && reply.state) applyWorkerState(reply.state);
}

/**
 * Ask the browser to keep this origin's storage.
 *
 * Without it, saved chapters live in "best effort" storage the browser may
 * clear under pressure — precisely the bytes the user asked to keep. Chrome
 * grants it silently on an engaged/installed origin, Firefox prompts, and
 * Safari has no such API and treats an installed web app as persistent already,
 * so a `false` here is not an error, only an unmet request.
 */
export async function requestPersistentStorage(): Promise<boolean> {
  if (typeof window === "undefined" || !window.navigator.storage?.persist) return false;
  try {
    if (await window.navigator.storage.persisted()) return true;
    return await window.navigator.storage.persist();
  } catch {
    return false;
  }
}

export async function saveChapterOffline(request: SaveChapterRequest): Promise<OfflineReply> {
  void requestPersistentStorage();
  return ask({ type: OFFLINE_MESSAGE.saveChapter, payload: request });
}

export function cancelChapterSave(key: string): Promise<OfflineReply> {
  return ask({ type: OFFLINE_MESSAGE.cancelSave, key });
}

export function removeSavedChapter(scope: StorageScope, key: string): Promise<OfflineReply> {
  return ask({ type: OFFLINE_MESSAGE.removeChapter, scope, key });
}

export function markChapterOpened(scope: StorageScope, key: string): Promise<OfflineReply> {
  return ask({ type: OFFLINE_MESSAGE.markOpened, scope, key });
}

export function markChapterFinished(scope: StorageScope, key: string): Promise<OfflineReply> {
  return ask({ type: OFFLINE_MESSAGE.markFinished, scope, key });
}

export function markChapterClosed(key: string): Promise<OfflineReply> {
  return ask({ type: OFFLINE_MESSAGE.chapterClosed, key });
}

/** The launch/resume sweep: expiry first, then pressure eviction. */
export function sweepOffline(
  scope: StorageScope,
  protectKey: string | null,
): Promise<OfflineReply> {
  return ask({ type: OFFLINE_MESSAGE.sweep, scope, protectKey });
}

export function setOfflineRetention(
  scope: StorageScope,
  retentionMs: number | null,
): Promise<OfflineReply> {
  return ask({ type: OFFLINE_MESSAGE.setRetention, scope, retentionMs });
}

export function clearOfflineScope(scope: StorageScope): Promise<OfflineReply> {
  return ask({ type: OFFLINE_MESSAGE.clearScope, scope });
}

/**
 * The manual escape hatch. Unregisters the worker and drops every cache this
 * origin holds, so a caching bug can always be walked out of from inside the
 * app rather than from devtools.
 */
export async function resetServiceWorker(): Promise<void> {
  if (!isServiceWorkerSupported()) return;
  try {
    const registrations = await window.navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));
    const names = await window.caches.keys();
    await Promise.all(names.map((name) => window.caches.delete(name)));
  } finally {
    window.location.reload();
  }
}

let updateRequested = false;

/**
 * Activate a waiting worker, then reload once it takes over.
 *
 * The reload is armed only here: `controllerchange` also fires the first time a
 * worker claims a page, and reloading on that would bounce every visitor once
 * on their first visit for no reason.
 */
export async function applyWorkerUpdate(waiting: ServiceWorker): Promise<void> {
  if (updateRequested) return;
  updateRequested = true;
  window.navigator.serviceWorker.addEventListener(
    "controllerchange",
    () => {
      window.location.reload();
    },
    { once: true },
  );
  waiting.postMessage({ type: OFFLINE_MESSAGE.skipWaiting });
}
