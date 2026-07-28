/**
 * Guard for the 18+ write path.
 *
 * `PUT /settings` writes the PER-PROFILE `mature_content_enabled` when the
 * request carries `X-Profile-Id`, and the instance-wide default when it does
 * not (backend/routes/settings.py:138-147). Those are very different writes:
 * the global value is only a fallback for profiles that have no value of their
 * own and the seed for profiles created later, so a profile-less session that
 * "turns 18+ on" changes nothing it can see while quietly re-arming the default
 * for everyone else. That mismatch is how the gate was defeated before.
 *
 * The web client therefore refuses to send the write at all unless it can name
 * the profile the setting belongs to, and says why instead of failing silently.
 */

export const MATURE_TOGGLE_NO_PROFILE_REASON =
  "This setting belongs to a reading profile, and none is active. " +
  "Choose a profile first — writing it now would change the server-wide " +
  "default for every profile instead of yours.";

/** The reason the mature toggle cannot be written, or null when it can be. */
export function matureToggleBlockReason(activeProfileId: number | null): string | null {
  return activeProfileId === null ? MATURE_TOGGLE_NO_PROFILE_REASON : null;
}
