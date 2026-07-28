import { http } from "@/services/http";
import type { SystemStatus } from "@/services/system";

/**
 * Backend liveness probe for the status page.
 *
 * `GET /health` is the JSON health route (backend/routes/system.py:43) and one
 * of the few endpoints on the public allowlist
 * (backend/services/auth_service.py:335-345), so it answers even when the
 * session has expired — which is precisely when the owner most wants to know
 * whether the server itself is up. `GET /` returns the same payload but serves
 * an HTML install page to anything that accepts text/html, so the dedicated
 * probe is the honest choice here.
 */
export const statusApi = {
  health: () => http.get<SystemStatus>("/health"),
};
