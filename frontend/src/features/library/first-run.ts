/**
 * Pure decision logic for the first-run hint: a quiet strip that tells a
 * brand-new account (zero follows) to go browse a source, and disappears the
 * moment that stops being true. Kept free of React so it is unit-testable in
 * the node test environment (mirrors `profiles/access.ts`).
 *
 * Deliberately has no "dismissed" flag. The hint is driven entirely by
 * `followedCount`, so it is impossible for it to keep nagging after the
 * account it was about has follows — there is no stale dismissal to reset,
 * because there was never a dismissal at all.
 */

/** Routes where the hint would be redundant or in the way. */
function isSuppressedPath(pathname: string): boolean {
  // The followed-library shelf already renders its own full, dedicated
  // empty state with the same call to action — a second banner on top of it
  // would just be noise.
  if (pathname === "/library") return true;
  // Sources is the hint's own destination; showing "go browse Sources" while
  // already there says nothing new.
  if (pathname === "/sources" || pathname.startsWith("/sources/")) return true;
  return false;
}

export interface FirstRunHintInput {
  /** Number of followed series, or `null` while that count is unknown (loading/errored). */
  followedCount: number | null;
  pathname: string;
}

export function shouldShowFirstRunHint({
  followedCount,
  pathname,
}: FirstRunHintInput): boolean {
  if (followedCount === null || followedCount > 0) return false;
  return !isSuppressedPath(pathname);
}
