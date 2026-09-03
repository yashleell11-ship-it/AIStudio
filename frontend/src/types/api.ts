/**
 * Shared contracts for talking to the FastAPI backend.
 * Every request resolves to data of type T or throws an `ApiError`.
 */

export interface ApiErrorBody {
  /** Stable machine-readable code, e.g. "not_found". */
  code: string;
  /** Human-readable message safe to surface in the UI. */
  message: string;
  /** Optional structured details (validation errors, etc.). */
  details?: unknown;
}

/** Thrown by the HTTP client for any non-2xx response or transport failure. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: unknown;

  constructor(status: number, body: Partial<ApiErrorBody>) {
    super(body.message ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code ?? "unknown_error";
    this.details = body.details;
  }
}

/**
 * Source-native domain identity (spec §2). A series is `(sourceId, seriesKey)`;
 * a chapter adds `chapterKey`. Keys are opaque connector strings that routinely
 * contain `/` — never concatenate them into a path, always pass them as query
 * params (URL-encoded by `URLSearchParams`) or `encodeURIComponent` each path
 * segment.
 */
export interface SeriesId {
  sourceId: string;
  seriesKey: string;
}

export interface ChapterId extends SeriesId {
  chapterKey: string;
}

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RequestOptions {
  method?: HttpMethod;
  /** JSON-serializable request body. */
  body?: unknown;
  /** Query string parameters; undefined/null values are skipped. */
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}
