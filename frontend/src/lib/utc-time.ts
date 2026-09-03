/**
 * Parsing for the timestamps the API returns.
 *
 * Every timestamp the backend emits is UTC, but most are serialised from a
 * NAIVE `datetime` (see `backend/core/time_utils.py`: the instant is computed
 * tz-aware and the tzinfo is then dropped to match the DB columns), so the
 * string carries no `Z` and no offset. `Date.parse` reads a date-time string
 * with no designator as LOCAL time, which silently shifts every derived age by
 * the viewer's UTC offset — "3 minutes ago" reads as "5 hours ago" in IST.
 */

/** A trailing `Z`, or a `+05:30` / `-0800` style offset. */
const HAS_DESIGNATOR = /(?:[Zz]|[+-]\d{2}:?\d{2})$/;
/** A time component at all — a date-only string is already parsed as UTC. */
const HAS_TIME = /\d{2}:\d{2}/;

/**
 * Milliseconds since the epoch for a backend timestamp, or `null` when the
 * value is missing or unparseable (a data problem, never a reason to render
 * `NaN` at the user).
 */
export function parseUtcTimestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  // SQLite-style "2026-09-04 03:00:00" is not reliably parseable; ISO is.
  const isoish = value.trim().replace(" ", "T");
  const normalized =
    HAS_TIME.test(isoish) && !HAS_DESIGNATOR.test(isoish) ? `${isoish}Z` : isoish;
  const parsed = Date.parse(normalized);
  return Number.isNaN(parsed) ? null : parsed;
}
