import type { SeriesSummary } from "./types";

/**
 * Advisory duplicate detection over the followed library.
 *
 * Search spans ~18 sources, so following the same series twice — once from each
 * of two sites — is easy and invisible: the two rows have different ids,
 * different chapter counts and different covers, and only the title gives them
 * away.
 *
 * Strictly advisory. The owner asked that duplicates stay allowed so each copy
 * keeps notifying separately, so nothing here merges, unfollows or reorders
 * anything — it only groups, and the view offers the unfollow the user may or
 * may not want.
 */

/**
 * Mirrors `_normalize_title` in backend/services/browse_service.py:77-79 —
 * collapse internal whitespace, trim, casefold — so the client groups exactly
 * what the server would consider the same title within a source.
 *
 * `toLowerCase` stands in for Python's `casefold`. They differ only on a handful
 * of scripts (German ß, Cherokee) that no title here uses, and disagreeing would
 * cost at most one missed suggestion.
 */
export function normalizeSeriesTitle(title: string): string {
  return title.replace(/\s+/g, " ").trim().toLowerCase();
}

export interface DuplicateGroup {
  /** The normalized title the group was keyed on. */
  key: string;
  /** The first member's title as written, for display. */
  title: string;
  /** Members, most-established first. See {@link findDuplicateSeries}. */
  series: SeriesSummary[];
}

/**
 * Rank within a group so the copy the user has actually invested in comes
 * first: most chapters read, then the more complete copy, then the one added
 * first. The view labels the head "keep" and offers to unfollow the rest, so
 * getting this backwards would suggest throwing away the read one.
 */
function establishedFirst(a: SeriesSummary, b: SeriesSummary): number {
  if (a.read_chapters !== b.read_chapters) {
    return b.read_chapters - a.read_chapters;
  }
  if (a.chapter_count !== b.chapter_count) {
    return b.chapter_count - a.chapter_count;
  }
  if (a.created_at !== b.created_at) {
    return a.created_at < b.created_at ? -1 : 1;
  }
  return a.id - b.id;
}

/**
 * Group `items` by normalized title, keeping only titles held more than once.
 *
 * Groups come back in the order their first member appeared, so a list already
 * sorted by title yields suggestions in the order the user would scan them.
 * Blank titles are skipped: they would all collapse into one meaningless group.
 */
export function findDuplicateSeries(
  items: readonly SeriesSummary[],
): DuplicateGroup[] {
  const groups = new Map<string, SeriesSummary[]>();
  for (const series of items) {
    const key = normalizeSeriesTitle(series.title);
    if (key.length === 0) {
      continue;
    }
    const existing = groups.get(key);
    if (existing) {
      existing.push(series);
    } else {
      groups.set(key, [series]);
    }
  }

  const duplicates: DuplicateGroup[] = [];
  for (const [key, series] of groups) {
    if (series.length < 2) {
      continue;
    }
    const ranked = [...series].sort(establishedFirst);
    duplicates.push({ key, title: ranked[0].title, series: ranked });
  }
  return duplicates;
}

/** How many follows could be dropped if every suggestion were taken. */
export function duplicateSurplusCount(groups: readonly DuplicateGroup[]): number {
  return groups.reduce((total, group) => total + group.series.length - 1, 0);
}
