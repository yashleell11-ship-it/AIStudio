import { byline, formatChapterCount } from "./book";

/**
 * One book on a shelf.
 *
 * The shelf is the novel side's answer to the manga grid, and the reason it is
 * a different shape: a poster grid asks the cover to carry the identity, and a
 * novel's cover is usually an aggregator's generated placeholder. What a reader
 * actually recognises a novel by is its title, its author and its length, so
 * those are the row — with the cover kept small and subordinate rather than
 * dropped, since when there IS real art it still aids recognition.
 *
 * Deliberately a view model rather than a source shape: browse rows
 * (`SourceSeriesSummary`) and library rows (`FollowedSeries`) carry different
 * fields, and the shelf renders both.
 */
export interface ShelfBook {
  /** React key, and the identity the shelf de-duplicates on. */
  key: string;
  href: string;
  title: string;
  author: string | null;
  description: string | null;
  chapterCount: number | null;
  /** Publication status as the source words it ("ongoing", "Completed"). */
  status: string | null;
  genres: readonly string[];
  /** Already resolved to a fetchable URL by the caller, or null for none. */
  coverUrl: string | null;
  /** Anything shelf-specific worth a line: "Reading · 42%", "Favourite". */
  note: string | null;
}

/**
 * The one metadata line under a shelf title, as parts to join.
 *
 * Empty parts are dropped rather than rendered as stray separators — a source
 * that reports no author and no chapter count should produce a title with
 * nothing under it, not "by  ·  · ".
 */
export function shelfMetaParts(book: ShelfBook): string[] {
  const parts = [
    byline(book.author),
    formatChapterCount(book.chapterCount),
    formatStatus(book.status),
    book.note?.trim() || null,
  ];
  return parts.filter((part): part is string => Boolean(part));
}

/**
 * "ongoing" → "Ongoing". Sources are inconsistent about case and the status is
 * set beside a byline, where a lowercase word reads as a typo.
 */
export function formatStatus(status: string | null | undefined): string | null {
  const trimmed = status?.trim();
  if (!trimmed) return null;
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

/**
 * Genres, capped and de-duplicated.
 *
 * Novel aggregators tag generously — twenty genres on one book is normal — and
 * a row that wraps to four lines of tags is a row nobody reads. Six is enough
 * to characterise a book; the series page shows the rest.
 */
export const MAX_SHELF_GENRES = 6;

export function shelfGenres(
  genres: readonly string[] | null | undefined,
  limit = MAX_SHELF_GENRES,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const genre of genres ?? []) {
    const trimmed = genre.trim();
    if (!trimmed) continue;
    const fingerprint = trimmed.toLowerCase();
    if (seen.has(fingerprint)) continue;
    seen.add(fingerprint);
    out.push(trimmed);
    if (out.length >= limit) break;
  }
  return out;
}

/**
 * A blurb trimmed to a shelf row.
 *
 * The clamp itself is CSS (`line-clamp`), but the whitespace is not: connectors
 * hand back descriptions with newlines and runs of spaces left in from the
 * source's markup, and those turn a two-line clamp into a two-line gap.
 */
export function shelfBlurb(description: string | null | undefined): string | null {
  const collapsed = description?.replace(/\s+/g, " ").trim();
  return collapsed ? collapsed : null;
}
