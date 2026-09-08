import { parseUtcTimestamp } from "@/lib/utc-time";

/**
 * When a chapter went up, as a chapter row should say it.
 *
 * Recent chapters get a relative age, because "2d ago" is the thing a reader
 * checking for new chapters actually wants to know. Past a week the relative
 * form stops carrying information ("43d ago") and it becomes a date.
 *
 * The value is whatever the source published, and sources are not consistent:
 * an ISO instant from an API, a bare `YYYY-MM-DD`, or a scraped string that was
 * never a date at all. Anything unparseable is passed through UNCHANGED rather
 * than dropped, because the strings in that last group are already the sentence
 * the site showed a human ("2 days ago", "Yesterday"); blanking them would hide
 * information the source did provide.
 */
export function chapterDateLabel(
  value: string | null | undefined,
  nowMs: number = Date.now(),
): string | null {
  const raw = value?.trim();
  if (!raw) return null;

  const parsed = parseUtcTimestamp(raw);
  if (parsed === null) return raw;

  const days = Math.floor((nowMs - parsed) / 86_400_000);

  // A source's clock can sit ahead of ours, and a scheduled chapter is a real
  // thing. Neither is worth a "in 3 days" that the reader cannot act on.
  if (days < 0) return "Just now";
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(parsed).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
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
