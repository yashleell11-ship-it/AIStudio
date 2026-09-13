import { parseCalendarDay, parseUtcTimestamp } from "@/lib/utc-time";

/**
 * When a chapter went up, as a chapter row should say it.
 *
 * Recent chapters get a relative age, because "2d ago" is the thing a reader
 * checking for new chapters actually wants to know. Past a week the relative
 * form stops carrying information ("43d ago") and it becomes a date.
 *
 * The value is whatever the source published, and sources are not consistent:
 * an ISO instant from an API, a naive one with no designator, a bare
 * `YYYY-MM-DD`, or a scraped string that was never a date at all. Anything
 * unparseable is passed through UNCHANGED rather than dropped, because the
 * strings in that last group are already the sentence the site showed a human
 * ("2 days ago", "18 Mar 2021"); blanking them would hide information the
 * source did provide.
 *
 * Mirrored by the Flutter client in
 * `mobile/lib/features/sources/utils/chapter_date.dart`. Keep the two in step:
 * they disagreed on the day rule below for a release, and the test that was
 * supposed to catch it used midnight timestamps, where both rules agree.
 */
export function chapterDateLabel(
  value: string | null | undefined,
  nowMs: number = Date.now(),
): string | null {
  const raw = value?.trim();
  if (!raw) return null;

  const at = chapterInstant(raw);
  if (at === null) return raw;

  const days = calendarDaysBetween(at, new Date(nowMs));

  // A source's clock can sit ahead of ours, and a scheduled chapter is a real
  // thing. Neither is worth a "in 3 days" that the reader cannot act on.
  if (days < 0) return "Just now";
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return at.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * The shapes the BACKEND emits: a bare day, or a day plus a time with an
 * optional designator. Nothing else is treated as a date.
 *
 * The gate is explicit rather than "whatever the platform can parse", because
 * the platforms do not agree and that is precisely how the two clients drifted.
 * `Date.parse("Apr 22,2016")` succeeds in V8 and reformats it to "22 Apr 2016";
 * Dart's `DateTime.tryParse` returns null for the same string, so the Flutter
 * client rendered nothing. Connectors emit plenty of those — "18 Mar 2021"
 * (manhwa18), "Apr 22,2016" (mangatown), "Nov 05,2018" (fanfox), "2019/07/13"
 * (mangafreak). Under one shared rule both clients now show the source's own
 * wording verbatim instead of one guessing and the other giving up.
 */
const BACKEND_DATE =
  /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-]\d{2}:?\d{2})?)?$/;

/**
 * The instant a chapter date refers to, or `null` if the string is not one of
 * the shapes above — in which case the caller passes it through untouched.
 *
 * A bare `YYYY-MM-DD` is handled first and deliberately differently: it does not
 * name an instant, it names a DAY, so it is read as local midnight
 * (`parseCalendarDay`) rather than as UTC midnight. `Date.parse` reads a
 * date-only string as UTC, and anywhere west of Greenwich that lands on the
 * previous day — the off-by-one `parseCalendarDay` exists to prevent. Most of
 * what connectors scrape is exactly this shape.
 */
function chapterInstant(raw: string): Date | null {
  if (!BACKEND_DATE.test(raw)) return null;

  const day = parseCalendarDay(raw);
  if (day !== null) return day;

  const parsed = parseUtcTimestamp(raw);
  return parsed === null ? null : new Date(parsed);
}

/**
 * Calendar days between two instants, counted in the READER'S OWN zone.
 *
 * By date rather than by elapsed hours: a chapter posted at 23:00 last night is
 * "Yesterday", not "Today", even though it is only two hours old — that is how
 * someone scanning a list of dates reads it. This used to be
 * `floor((now - then) / 86400000)`, which called that chapter "Today" while the
 * Flutter client called it "Yesterday".
 */
function calendarDaysBetween(at: Date, reference: Date): number {
  const a = Date.UTC(at.getFullYear(), at.getMonth(), at.getDate());
  const b = Date.UTC(
    reference.getFullYear(),
    reference.getMonth(),
    reference.getDate(),
  );
  return Math.round((b - a) / 86_400_000);
}

/**
 * The date field a chapter carries, whichever of the two names it uses.
 *
 * A live source listing serializes it as `release_date`
 * (`BrowseService._serialize_chapter`); the cached chapter list normalises the
 * same value to `published_at` (`SourceCacheService._merge_series_row`). One
 * reader, so a row from either path renders the same way.
 */
export function chapterUploadedAt(chapter: {
  release_date?: string | null;
  published_at?: string | null;
}): string | null {
  return chapter.release_date ?? chapter.published_at ?? null;
}
