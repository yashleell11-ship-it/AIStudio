import { env } from "@/config/env";
import { getActiveProfileId } from "@/features/profiles/store";
import { ApiError, type ApiErrorBody, type RequestOptions } from "@/types/api";

/**
 * Resolve the API base to an absolute URL.
 *
 * - Absolute base (e.g. dev's `http://127.0.0.1:8000`): used as-is.
 * - Relative base (e.g. prod's same-origin `/api`): resolved against the
 *   current origin, so the browser calls same-origin and Next.js proxies
 *   `/api/*` to the backend. API calls only run in the browser, so `window`
 *   is available; on the server we fall back to the raw value.
 */
function resolveApiBase(): string {
  const base = env.apiUrl;
  if (/^https?:\/\//i.test(base)) return base;
  if (typeof window !== "undefined") return `${window.location.origin}${base}`;
  return base;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(path.replace(/^\//, ""), ensureTrailingSlash(resolveApiBase()));
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

function ensureTrailingSlash(value: string): string {
  return value.endsWith("/") ? value : `${value}/`;
}

/**
 * Build the `{source, series, chapter}` query object every source-native
 * endpoint takes (spec §2). Values are passed through untouched — `buildUrl`
 * feeds them to `URLSearchParams`, which percent-encodes, so opaque keys
 * containing `/` survive the round trip. `chapter` is omitted when absent.
 */
export function sourceChapterQuery(ref: {
  sourceId: string;
  seriesKey: string;
  chapterKey?: string;
}): Record<string, string> {
  const query: Record<string, string> = {
    source: ref.sourceId,
    series: ref.seriesKey,
  };
  if (ref.chapterKey !== undefined) {
    query.chapter = ref.chapterKey;
  }
  return query;
}

/**
 * Percent-encode an opaque connector key for use as a single path segment,
 * preserving the slash-separated form the backend's `:path` converters expect
 * (each sub-segment encoded, joined by raw `/`).
 */
export function encodePathKey(key: string): string {
  return key.split("/").map(encodeURIComponent).join("/");
}

/**
 * Typed fetch wrapper. Resolves to parsed JSON of type T or throws `ApiError`.
 * This is the single entry point for backend calls — feature services build on it.
 */
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, query, signal, headers } = options;

  // Attach the active reading profile so the backend scopes reads and enforces
  // mutations per-profile. The id lives in client state (zustand); reading it
  // here means every call carries `X-Profile-Id` automatically, with no
  // per-call threading. `null` before a profile is chosen (or on the server) —
  // then the header is omitted. An explicit `headers` override still wins.
  const profileId = getActiveProfileId();

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      signal,
      // Send the httpOnly `mm_session` cookie on every request so authenticated
      // routes see the session. The web client holds no token — the cookie is
      // the credential.
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(profileId !== null ? { "X-Profile-Id": String(profileId) } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (cause) {
    throw new ApiError(0, {
      code: "network_error",
      message: "Could not reach the server. Is the backend running?",
      details: cause,
    });
  }

  if (!response.ok) {
    throw new ApiError(response.status, await safeParseError(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function safeParseError(response: Response): Promise<Partial<ApiErrorBody>> {
  try {
    return (await response.json()) as Partial<ApiErrorBody>;
  } catch {
    return { message: response.statusText };
  }
}

export const http = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method">) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method">) =>
    request<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method">) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, "method">) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
