import { ApiError } from "@/types/api";
import { parseUtcTimestamp } from "@/lib/utc-time";
import type { AccountSession, ChangePasswordPayload } from "./types";

/**
 * Pure account-security policy: the decisions behind the change-password form
 * and the active-sessions list. Kept free of React so it is unit-testable in
 * the node test environment (the repo has no DOM test renderer).
 *
 * Nothing here ever stores, logs, or returns a password — `toChangePasswordPayload`
 * is the only function that touches one, and it only hands it to the request body.
 */

/** Mirrors `MIN_PASSWORD_LENGTH` / `MAX_PASSWORD_LENGTH` in `backend/core/auth.py`. */
export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 4096;

/** What the change-password form collects before submitting. */
export interface ChangePasswordFormValues {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}

export type ChangePasswordField = keyof ChangePasswordFormValues;

export const CHANGE_PASSWORD_FIELDS: readonly ChangePasswordField[] = [
  "currentPassword",
  "newPassword",
  "confirmPassword",
] as const;

/**
 * Client-side pre-flight for `POST /auth/change-password`, or `null` when the
 * form is submittable. This is a courtesy, never the enforcement: the server
 * re-checks length itself and is the only thing that can check the current
 * password. The length wording is copied verbatim from
 * `validate_password_strength` so the two can never contradict each other.
 *
 * "Must differ from the current one" is stricter than the server, which would
 * happily re-hash the same secret — but a password change that changes nothing
 * still signs every other device out, so it is worth catching a double paste.
 */
export function validateChangePassword(values: ChangePasswordFormValues): string | null {
  if (values.currentPassword === "") return "Enter your current password.";
  if (values.newPassword === "") return "Enter a new password.";
  if (values.newPassword.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (values.newPassword.length > MAX_PASSWORD_LENGTH) return "Password is too long.";
  if (values.newPassword !== values.confirmPassword) {
    return "The new passwords don't match.";
  }
  if (values.newPassword === values.currentPassword) {
    return "Your new password must be different from your current one.";
  }
  return null;
}

/**
 * Body for `POST /auth/change-password`. `confirmPassword` never leaves the
 * client — it exists only to catch a typo in a secret the user cannot see.
 */
export function toChangePasswordPayload(
  values: ChangePasswordFormValues,
): ChangePasswordPayload {
  return {
    current_password: values.currentPassword,
    new_password: values.newPassword,
  };
}

/**
 * Which password fields to wipe from component state after a REJECTED attempt.
 * (A successful one always wipes all three — the secret has no further use.)
 *
 * The settings page can stay mounted for hours, so a submitted password should
 * not linger, but blanking the whole form over one mistyped character is its
 * own kind of hostile. The server's error code says which secret was actually
 * at fault, so only that one is cleared; an unrecognised failure clears
 * everything, because then we do not know what happened.
 */
export function fieldsToClearAfterFailure(error: unknown): ChangePasswordField[] {
  if (error instanceof ApiError) {
    // 401 invalid_credentials: the current password was wrong (auth_service.change_password).
    if (error.code === "invalid_credentials") return ["currentPassword"];
    // 422 weak_password: the new password failed validate_password_strength.
    if (error.code === "weak_password") return ["newPassword", "confirmPassword"];
  }
  return [...CHANGE_PASSWORD_FIELDS];
}

/**
 * User-facing copy for a failed auth request.
 *
 * Deliberately a pass-through for anything the server said: the backend has
 * already decided how much to disclose ("Current password is incorrect."), and
 * re-wording it here risks either leaking more than it chose to or contradicting
 * it. Only a failure that produced no server message at all — a transport
 * error, a thrown non-`ApiError` — gets local copy.
 */
export function describeAuthError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  return fallback;
}

/** Platform patterns, most specific first — iPadOS Safari also matches Macintosh. */
const PLATFORMS: ReadonlyArray<readonly [RegExp, string]> = [
  [/Android/i, "Android"],
  [/iPhone/i, "iPhone"],
  [/iPad/i, "iPad"],
  [/CrOS/i, "ChromeOS"],
  [/Macintosh|Mac OS X/i, "macOS"],
  [/Windows/i, "Windows"],
  [/Linux/i, "Linux"],
];

/** Browser patterns, most specific first — every Chromium UA also says Safari. */
const BROWSERS: ReadonlyArray<readonly [RegExp, string]> = [
  [/Edg\//i, "Edge"],
  [/OPR\/|Opera/i, "Opera"],
  [/Firefox\/|FxiOS\//i, "Firefox"],
  [/Chrome\/|CriOS\//i, "Chrome"],
  [/Safari\//i, "Safari"],
];

function matchFirst(
  patterns: ReadonlyArray<readonly [RegExp, string]>,
  value: string,
): string | null {
  for (const [pattern, label] of patterns) {
    if (pattern.test(value)) return label;
  }
  return null;
}

/**
 * A short human label for the `user_agent` the backend recorded at login.
 *
 * A raw UA string is unreadable, and the whole point of the session list is
 * that someone can recognise their own devices in it and spot one that is not
 * theirs. The Flutter client sends no UA of its own, so it arrives as Dart's
 * default (`Dart/3.5 (dart:io)`) — named as the app rather than left looking
 * like a stray script.
 */
export function describeSessionDevice(userAgent: string | null | undefined): string {
  const value = userAgent?.trim();
  if (!value) return "Unknown device";
  if (/^Dart\//i.test(value)) return "ManhwaManiacs app";

  const platform = matchFirst(PLATFORMS, value);
  const browser = matchFirst(BROWSERS, value);
  if (browser && platform) return `${browser} on ${platform}`;
  return browser ?? platform ?? "Unknown device";
}

/**
 * Display order: this device first, then most recently used. The endpoint
 * already sorts by `last_used_at` desc, but the current session has to lead
 * regardless of when it was last touched — it is the row whose meaning differs
 * from every other, and it should not be somewhere down the list when the user
 * goes looking for the ones to revoke.
 */
export function sortSessionsForDisplay(sessions: readonly AccountSession[]): AccountSession[] {
  return [...sessions].sort((a, b) => {
    if (a.current !== b.current) return a.current ? -1 : 1;
    return (parseUtcTimestamp(b.last_used_at) ?? 0) - (parseUtcTimestamp(a.last_used_at) ?? 0);
  });
}

export type SessionRowAction = "sign-out-current" | "revoke";

/**
 * What the button on a session row does.
 *
 * `DELETE /auth/sessions/{id}` will happily delete the caller's own session,
 * which drops the browser into a signed-out app with no explanation and a
 * stale cache. So the current row does not offer "Revoke" at all: it offers
 * the ordinary sign-out, which clears the cached queries and lands on /login.
 */
export function sessionRowAction(session: Pick<AccountSession, "current">): SessionRowAction {
  return session.current ? "sign-out-current" : "revoke";
}

/**
 * Whether "Sign out everywhere" may fire. It revokes EVERY session including
 * this one, so it is gated on an explicit acknowledgement rather than being a
 * single click next to the ordinary controls.
 */
export function canSignOutEverywhere(acknowledged: boolean, pending: boolean): boolean {
  return acknowledged && !pending;
}
