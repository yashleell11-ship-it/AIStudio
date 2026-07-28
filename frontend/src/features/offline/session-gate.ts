import { ApiError } from "@/types/api";

/**
 * Whether the app may render when `/auth/me` could not be asked.
 *
 * This is the last mile of offline reading, and without it everything else in
 * this feature is decorative. A cold start with no network goes: cached
 * document renders → the shell probes `/auth/me` → the probe fails → the guard
 * sees no user and sends the reader to /login → the login screen also needs the
 * server. Chapters sitting on the device, unreachable.
 *
 * The distinction that fixes it is one the guard did not previously need: a 401
 * is an ANSWER ("you are not signed in", redirect), a network failure is the
 * ABSENCE of an answer ("we could not ask"). `useCurrentUser` already turns 401
 * into `null`, so a thrown network error is unambiguous — it cannot be a
 * rejected session.
 *
 * Admitting on an unanswered probe is not a way past the login screen. The
 * session cookie is httpOnly and still required by every request; the moment
 * the network is back the probe resolves and a genuinely signed-out visitor is
 * redirected. What renders in the meantime is the shell plus whatever this
 * device already stored — which is the profile's own saved chapters, in the
 * profile's own cache, on the profile's own device.
 */

/** A request that never reached the server (see `services/http.ts`'s catch). */
export function isNetworkUnreachableError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0;
}

export type SessionGate =
  /** The probe is still in flight. */
  | "pending"
  /** A session was resolved. */
  | "admit"
  /** No answer, because there is no network. Render, on last known state. */
  | "admit-offline"
  /** Answered: not signed in. */
  | "redirect";

export function resolveSessionGate(input: {
  isLoading: boolean;
  hasUser: boolean;
  error: unknown;
}): SessionGate {
  if (input.hasUser) return "admit";
  if (input.isLoading) return "pending";
  if (isNetworkUnreachableError(input.error)) return "admit-offline";
  return "redirect";
}

/** True while the shell should show the "checking" screen instead of the app. */
export function isSessionUnresolved(gate: SessionGate): boolean {
  return gate === "pending" || gate === "redirect";
}
