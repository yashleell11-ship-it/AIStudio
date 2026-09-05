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


/**
 * Every query-key root holding data the backend filters by the profile's 18+
 * gate, and which therefore has to be dropped when the gate is flipped.
 *
 * `sources` covers the installed-source list and federated search
 * (`BrowseService` is 18+ scoped); `library` and `library-discovery` cover
 * everything that goes through `FollowedSeriesService._visible` — the library
 * grid, the followed index, library search, the continue-reading strip,
 * history, statistics and recommendations; `bookmarks`, `updates`, `ocr` and
 * `reader` each front a service that applies `mature_tracker_case` to its own
 * table (`BookmarkService`, `UpdateService`, `OcrIngestService`,
 * `ProgressService`); `novels` is served through the same per-caller gate
 * before any cache row is read; `preferences` is the flag itself.
 *
 * This list has now drifted twice. It once named `intelligence`, the discovery
 * root's name BEFORE the source-native rewrite renamed it to
 * `library-discovery`, and no longer named `library` at all — invalidating a
 * root nothing is cached under matches nothing, so turning the gate off and
 * walking straight to the library kept listing adult titles out of cache. Then
 * bookmarks, novels, OCR and updates were each added as their own root and none
 * of them was added here. `mature-gate.test.ts` now reads every root declared
 * anywhere in `src/` off disk and fails unless it appears in this list or in
 * {@link NOT_MATURE_GATED_QUERY_ROOTS}, so a new feature cannot be given a
 * cache root without someone deciding which of the two it is.
 */
export const MATURE_GATED_QUERY_ROOTS = [
  "preferences",
  "sources",
  "library",
  "library-discovery",
  "bookmarks",
  "novels",
  "ocr",
  "updates",
  "reader",
] as const;

/**
 * The roots deliberately left alone, and why — the other half of the partition
 * the drift test checks.
 *
 * None of these carries series content: `auth` is the session, `profiles` is
 * the account's own profile list, `backup` is the instance snapshot's status
 * and `status` is instance health. Flipping the 18+ gate cannot change a single
 * field in any of them.
 */
export const NOT_MATURE_GATED_QUERY_ROOTS = [
  "auth",
  "profiles",
  "backup",
  "status",
] as const;

/**
 * Drop every 18+-filtered cache. Typed structurally rather than against
 * `QueryClient` so this module stays free of React and testable in the node
 * environment, like the rest of the gate.
 */
export function invalidateMatureGatedQueries(client: {
  invalidateQueries: (filters: { queryKey: readonly unknown[] }) => unknown;
}): void {
  for (const root of MATURE_GATED_QUERY_ROOTS) {
    void client.invalidateQueries({ queryKey: [root] });
  }
}
