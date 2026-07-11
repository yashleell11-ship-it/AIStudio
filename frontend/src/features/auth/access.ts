import { ApiError } from "@/types/api";
import type { BootstrapStatus } from "./types";

/**
 * Pure auth-access policy: predicates and screen-mode decisions shared by the
 * guard, the global 401 handler, and the login/register screens. Kept free of
 * React so it is unit-testable in the node test environment.
 */

/** Routes that render without a session (the guard never redirects away from them). */
export const PUBLIC_AUTH_PATHS = ["/login", "/register"] as const;

/** True when `pathname` is a public auth route that must render unauthenticated. */
export function isPublicAuthPath(pathname: string): boolean {
  return (PUBLIC_AUTH_PATHS as readonly string[]).includes(pathname);
}

/** A request failed because the session is missing or expired (HTTP 401). */
export function isUnauthorizedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/**
 * Whether a query key belongs to the auth namespace (`["auth", ...]`). The
 * global 401 handler skips these: `/auth/me` resolves 401 to `null` itself and
 * `/auth/bootstrap-status` is public, so neither should trigger a redirect —
 * this is what prevents a redirect loop.
 */
export function isAuthQueryKey(queryKey: readonly unknown[]): boolean {
  return queryKey[0] === "auth";
}

export type AuthScreenMode = "bootstrap" | "login";

/**
 * The login screen doubles as first-run setup: when no account exists yet the
 * instance needs its first (admin) account, so it shows the bootstrap
 * create-admin form instead of the sign-in form.
 */
export function resolveLoginScreenMode(status: BootstrapStatus): AuthScreenMode {
  return status.needs_bootstrap ? "bootstrap" : "login";
}

export type RegisterAvailability = "bootstrap" | "open" | "closed";

/**
 * Whether the register page can accept a new account:
 * - `"bootstrap"`: no users yet — the first account becomes the administrator.
 * - `"open"`: users exist and self-service registration is enabled.
 * - `"closed"`: users exist and self-service registration is disabled.
 */
export function resolveRegisterAvailability(status: BootstrapStatus): RegisterAvailability {
  if (status.needs_bootstrap) return "bootstrap";
  return status.registration_enabled ? "open" : "closed";
}
