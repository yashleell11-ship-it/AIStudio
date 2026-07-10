/**
 * Runtime environment configuration for the web client.
 *
 * `NEXT_PUBLIC_API_URL` is inlined at build time and must point at the
 * ManhwaManiacs backend. In production it is the same-origin path `/api`
 * (resolved against `window.origin` in `services/http.ts`, then proxied to the
 * backend by Next.js — see `next.config.ts`). Falls back to the local dev
 * backend when unset, mirroring the mobile client's `Env.defaultApiUrl` (see
 * `mobile/lib/core/config/env.dart`).
 */
const DEFAULT_API_URL = "http://127.0.0.1:8000";

const rawApiUrl = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL;

export const env = {
  /** Base URL of the backend API, without a trailing slash. */
  apiUrl: rawApiUrl.replace(/\/+$/, ""),
} as const;
