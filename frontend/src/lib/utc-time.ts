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

/**
 * The other half of the same hazard: a backend CALENDAR DAY, not a timestamp.
 *
 * `GET /library/statistics` buckets its daily series and its streak at the
 * caller's own UTC offset (`tz_offset_minutes`) and returns the resulting LOCAL
 * day as a bare `"YYYY-MM-DD"`. The shift has already happened server-side, so
 * these strings must NOT go through `parseUtcTimestamp`: `Date.parse` reads a
 * date-only string as UTC midnight, and rendering that instant anywhere west of
 * Greenwich lands on the previous day — the same off-by-one this module exists
 * to prevent, running the other way.
 *
 * The parts are therefore read straight out of the string and handed to the
 * LOCAL `Date` constructor, which never shifts them.
 *
 * Returns `null` for anything that is not a real calendar date, so an
 * impossible day (`2026-02-31`) is rejected rather than silently rolled over
 * into March by the `Date` constructor.
 */
const CALENDAR_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

export function parseCalendarDay(value: string | null | undefined): Date | null {
  if (!value) return null;
  const match = CALENDAR_DAY.exec(value.trim());
  if (!match) return null;
  const [, year, month, day] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  // `new Date(2026, 1, 31)` is March 3rd, not an error. Round-trip to reject it.
  if (
    date.getFullYear() !== Number(year) ||
    date.getMonth() !== Number(month) - 1 ||
    date.getDate() !== Number(day)
  ) {
    return null;
  }
  return date;
}

export interface CalendarDayFormatOptions extends UtcFormatOptions {
  /** Passed straight to `toLocaleDateString`; defaults to the locale's short date. */
  format?: Intl.DateTimeFormatOptions;
}

/** Locale date for a backend `"YYYY-MM-DD"` bucket label. */
export function formatCalendarDay(
  value: string | null | undefined,
  { missing = "", invalid = "", format }: CalendarDayFormatOptions = {},
): string {
  if (!value) return missing;
  const date = parseCalendarDay(value);
  if (date === null) return invalid;
  return date.toLocaleDateString(undefined, format);
}
