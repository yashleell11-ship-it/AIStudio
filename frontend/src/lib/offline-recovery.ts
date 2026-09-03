/**
 * When a screen showing an offline state should re-run its own query.
 *
 * The offline empty states used to be terminal: they told the reader the
 * server could not be reached and then sat there, with no retry and no reaction
 * to the connection coming back — you had to know to reload the page. React
 * Query's own reconnect handling does not cover the common half of this either,
 * because the request usually fails while `navigator.onLine` is still true (the
 * SERVER is unreachable, not the device), and no `online` event is ever coming.
 * So the state gets both: a real Try again button, and this.
 */

/**
 * Minimum gap between automatic retries. Flaky wifi fires `online` repeatedly,
 * and a burst of refetches per flap is worse than none.
 */
export const OFFLINE_RETRY_COOLDOWN_MS = 3_000;

export interface AutoRetryInput {
  /** `navigator.onLine` at the moment the event fired. */
  online: boolean;
  /** When this screen last retried, automatically or by hand. */
  lastRetryAt: number | null;
  now: number;
  cooldownMs?: number;
}

export function shouldAutoRetry({
  online,
  lastRetryAt,
  now,
  cooldownMs = OFFLINE_RETRY_COOLDOWN_MS,
}: AutoRetryInput): boolean {
  // An `online` event that arrives with the browser already offline again is a
  // flap, not a recovery.
  if (!online) return false;
  if (lastRetryAt === null) return true;
  return now - lastRetryAt >= cooldownMs;
}

/**
 * The one sentence every offline state ends with. Split out so the ten screens
 * that render one cannot drift apart on the single fact that matters: what
 * still works without a connection.
 */
export const OFFLINE_DOWNLOADS_NOTE =
  "Chapters you've downloaded still open with no connection at all.";

/** The full description for an offline state, from its screen-specific lead. */
export function offlineDescription(reason: string): string {
  const lead = reason.trim();
  if (!lead) return OFFLINE_DOWNLOADS_NOTE;
  return `${lead} ${OFFLINE_DOWNLOADS_NOTE}`;
}
