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

/**
 * True when an uninvited registration right now would succeed and become the
 * admin/owner: zero accounts exist AND (per the backend) the takeover window
 * is still open. `bootstrap_open` is what draws that line; a backend without
 * the field never had a window, so `needs_bootstrap` alone is the right
 * fallback for it.
 */
function isBootstrapOpen(status: BootstrapStatus): boolean {
  return status.bootstrap_open ?? status.needs_bootstrap;
}

/**
 * True when `POST /auth/register` could succeed right now at all — with a
 * valid invite code where one is required. Falls back to
 * `registration_enabled` on a backend that predates the field.
 */
function isRegistrationOpen(status: BootstrapStatus): boolean {
  return status.registration_open ?? status.registration_enabled;
}

export type AuthScreenMode = "bootstrap" | "login";

/**
 * The login screen doubles as first-run setup: while the bootstrap takeover
 * window is open it shows the create-admin form instead of the sign-in form.
 * Once that window has expired, an empty instance falls back to the ordinary
 * sign-in screen — registering then follows the normal open/closed +
 * invite-code rules like any other account, even though it would still become
 * admin (see `AuthService.ensure_registration_allowed`).
 */
export function resolveLoginScreenMode(status: BootstrapStatus): AuthScreenMode {
  return isBootstrapOpen(status) ? "bootstrap" : "login";
}

export type RegisterAvailability = "bootstrap" | "open" | "closed";

/**
 * Whether the register page can accept a new account:
 * - `"bootstrap"`: the takeover window is open — this account becomes admin, no invite needed.
 * - `"open"`: a registration attempt could succeed (self-service enabled, invite code if required).
 * - `"closed"`: registration cannot succeed right now.
 */
export function resolveRegisterAvailability(status: BootstrapStatus): RegisterAvailability {
  if (isBootstrapOpen(status)) return "bootstrap";
  return isRegistrationOpen(status) ? "open" : "closed";
}

/**
 * Whether the register form should render its invite-code field. Only true
 * for open (non-bootstrap) registration when the server says a code is
 * required — an absent/undefined `invite_code_required` (older backend, or
 * the flag not landed yet) is treated as "not required", per the bootstrap
 * account never needing one either.
 */
export function shouldShowInviteField(status: BootstrapStatus): boolean {
  return resolveRegisterAvailability(status) === "open" && Boolean(status.invite_code_required);
}

/**
 * User-facing copy for a failed `POST /auth/register`. Every code the backend
 * is known to return gets plain, specific wording here rather than a generic
 * "something went wrong" — most importantly the two invite-code failures,
 * which must never look like an unexplained error. Anything not special-cased
 * (weak_password, invalid_username, validation_error, …) falls back to the
 * server's own message, which is already written for display.
 */
export function describeRegisterError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Could not create the account. Please try again.";
  }
  switch (error.code) {
    case "invite_code_required":
      return "An invite code is required to create an account on this instance.";
    case "invite_code_invalid":
      return "That invite code isn't valid. Check it and try again.";
    case "registration_disabled":
      return "Registration is currently closed on this instance.";
    case "username_taken":
      return "That username is already taken.";
    case "rate_limited":
      return "Too many attempts. Wait a moment and try again.";
    default:
      return error.message;
  }
}
