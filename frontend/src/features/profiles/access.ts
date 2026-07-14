/**
 * Pure profile-gate policy shared by the app shell and its tests. Kept free of
 * React so it is unit-testable in the node test environment (mirrors the
 * auth-access split).
 */

import { ApiError } from "@/types/api";

/** The full-bleed profile picker route. */
export const PROFILE_PICKER_PATH = "/profiles";

/**
 * A request failed because the active profile is missing (`profile_required`,
 * HTTP 400) or names a profile the account no longer owns (`profile_not_found`,
 * HTTP 404). Both mean the client's remembered selection is no longer valid, so
 * the caller should drop it and send the user back to the picker rather than
 * surface a raw error.
 */
export function isProfileScopeError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === "profile_required" || error.code === "profile_not_found")
  );
}

/** True when `pathname` is the picker itself (the gate must never redirect off it). */
export function isPickerPath(pathname: string): boolean {
  return pathname === PROFILE_PICKER_PATH;
}

export interface ProfileGateInput {
  /** The `/auth/me` probe has resolved to a signed-in user. */
  authenticated: boolean;
  /** The persisted active-profile selection has been restored from storage. */
  hydrated: boolean;
  /** An active profile is currently selected. */
  hasActiveProfile: boolean;
  /** The current route. */
  pathname: string;
}

/**
 * Whether to route to the picker. The picker runs AFTER auth (it never replaces
 * the remembered login): only a signed-in visitor whose active-profile state has
 * hydrated, who has not chosen a profile, and who is not already on the picker,
 * is redirected. Any other case renders in place.
 */
export function shouldRedirectToPicker({
  authenticated,
  hydrated,
  hasActiveProfile,
  pathname,
}: ProfileGateInput): boolean {
  if (!authenticated || !hydrated) return false;
  if (hasActiveProfile) return false;
  if (isPickerPath(pathname)) return false;
  return true;
}
