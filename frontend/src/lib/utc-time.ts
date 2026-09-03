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

/** Copy for a timestamp that is absent, and for one that will not parse. */
export interface UtcFormatOptions {
  /** Rendered when there is no value at all. */
  missing?: string;
  /** Rendered when a value is present but unparseable. */
  invalid?: string;
}

/**
 * Locale date+time for a backend timestamp.
 *
 * Every caller used to do `new Date(value).toLocaleString()` or
 * `Date.parse(value)` directly, which reads the backend's naive-UTC strings as
 * LOCAL time — the run that finished a minute ago rendered as 5.5h earlier in
 * IST, and a chapter read at 11pm was dated the previous day.
 */
export function formatUtcDateTime(
  value: string | null | undefined,
  { missing = "Never", invalid = "Unknown" }: UtcFormatOptions = {},
): string {
  if (!value) return missing;
  const parsed = parseUtcTimestamp(value);
  if (parsed === null) return invalid;
  return new Date(parsed).toLocaleString();
}

/** Locale date (no time) for a backend timestamp. */
export function formatUtcDate(
  value: string | null | undefined,
  { missing = "", invalid = "" }: UtcFormatOptions = {},
): string {
  if (!value) return missing;
  const parsed = parseUtcTimestamp(value);
  if (parsed === null) return invalid;
  return new Date(parsed).toLocaleDateString();
}

/**
 * Signed minutes between `nowMs` and a backend timestamp — positive for the
 * past, negative for the future — or `null` when it cannot be read.
 */
export function utcMinutesFromNow(
  value: string | null | undefined,
  nowMs: number,
): number | null {
  const parsed = parseUtcTimestamp(value);
  if (parsed === null) return null;
  return Math.round((nowMs - parsed) / 60_000);
}
