/**
 * The localStorage key the active-profile selection persists under.
 *
 * Its own module so the theme boot script can read the key name without
 * importing `store.ts` — that would drag zustand and React into a file whose
 * whole job is to emit a string into `<head>` before either exists on the page.
 * One constant, one owner, and the two cannot drift.
 */
export const ACTIVE_PROFILE_STORAGE_KEY = "mm.active-profile";
