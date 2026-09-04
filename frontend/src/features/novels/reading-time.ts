/**
 * Word counts and reading-time estimates.
 *
 * A novel chapter list has no page count worth showing — the connector reports
 * `page_count: 0` for every novel chapter, because a novel chapter is not made
 * of pages. What a reader actually wants to know before opening one is how
 * long it is, so the list shows words and minutes instead.
 *
 * 250 wpm is the conventional adult silent-reading rate for prose. It is an
 * estimate and is labelled as one ("~12 min"); nothing depends on it being
 * exact.
 */

export const WORDS_PER_MINUTE = 250;

/** Whole minutes at {@link WORDS_PER_MINUTE}, never less than 1 for real text. */
export function readingMinutes(wordCount: number): number {
  if (!Number.isFinite(wordCount) || wordCount <= 0) return 0;
  return Math.max(1, Math.round(wordCount / WORDS_PER_MINUTE));
}

/**
 * "~8 min" / "~1 h 12 min". Hours once past 90 minutes, because "~104 min" is
 * a number a reader has to do arithmetic on.
 */
export function formatReadingTime(wordCount: number): string | null {
  const minutes = readingMinutes(wordCount);
  if (minutes <= 0) return null;
  if (minutes <= 90) return `~${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `~${hours} h` : `~${hours} h ${rest} min`;
}

/** "1,240 words". Thousands separated by locale, singular respected. */
export function formatWordCount(wordCount: number): string | null {
  if (!Number.isFinite(wordCount) || wordCount <= 0) return null;
  const rounded = Math.round(wordCount);
  return `${rounded.toLocaleString()} ${rounded === 1 ? "word" : "words"}`;
}

/** "1,240 words · ~5 min" — the one line a novel chapter row shows. */
export function formatChapterLength(wordCount: number | null | undefined): string | null {
  if (wordCount == null) return null;
  const words = formatWordCount(wordCount);
  const time = formatReadingTime(wordCount);
  if (words === null) return null;
  return time === null ? words : `${words} · ${time}`;
}

/**
 * Words in a chapter's paragraphs, for a payload whose `word_count` did not
 * come through. Whitespace-split, which is what the backend counts too.
 */
export function countWords(paragraphs: readonly string[]): number {
  let total = 0;
  for (const paragraph of paragraphs) {
    const trimmed = paragraph.trim();
    if (trimmed.length === 0) continue;
    total += trimmed.split(/\s+/).length;
  }
  return total;
}
