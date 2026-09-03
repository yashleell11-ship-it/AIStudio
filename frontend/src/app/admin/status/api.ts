import { http } from "@/services/http";
import type { SystemStatus } from "@/services/system";

/** One source's recorded reachability (GET /sources/health). */
export interface SourceHealthRow {
  id: string;
  source_id: string;
  name: string;
  mature: boolean;
  health: {
    status: "ok" | "failing" | "dead" | "unknown";
    consecutive_failures: number;
    demoted: boolean;
    last_ok_at: string | null;
    last_error_at: string | null;
    last_error: string | null;
    last_checked_at: string | null;
  };
}

/**
 * Read-only inputs for the admin status page.
 *
 * `GET /health` is the JSON health route and one of the few endpoints on the
 * public allowlist, so it answers even when the session has expired — which is
 * precisely when the owner most wants to know whether the server itself is up.
 *
 * `GET /sources/health` is the per-source reachability record 1a added: the
 * same rows as `GET /sources`, ordered worst-first, so a source dying silently
 * is visible here instead of only when a followed series stops updating.
 */
export const statusApi = {
  health: () => http.get<SystemStatus>("/health"),
  sourceHealth: () => http.get<SourceHealthRow[]>("/sources/health"),
};
