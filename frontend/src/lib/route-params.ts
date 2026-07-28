/**
 * Decode a dynamic route segment exactly once, at the boundary.
 *
 * Next hands dynamic params back still percent-encoded, and nothing downstream
 * decoded them -- so a connector id containing a slash (Madara sources use
 * `series/chapter-1` shapes) was encoded again by every link builder and a
 * third time by the API client. The page answered 200 and showed the wrong
 * series, which is worse than a 404 because nothing looks broken.
 *
 * Decoding here means the rest of the app only ever handles real ids and every
 * link builder can encode unconditionally, which is the invariant that keeps
 * this from drifting back.
 *
 * A malformed sequence (a bare `%`) throws in decodeURIComponent; the raw value
 * is the best available answer in that case and still renders a not-found state
 * rather than a crashed route.
 */
export function decodeRouteParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
