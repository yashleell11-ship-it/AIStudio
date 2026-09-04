/**
 * The position maths, as pure functions.
 *
 * Both readers capture and restore through here, and both media use the same
 * four functions — which is the point of the server's one-anchor-set design:
 * a page and a paragraph are structurally the same thing (an integer index
 * into an ordered sequence, a fraction within the indexed unit, and the unit
 * count), so the degradation rule, the fraction-of-chapter maths and the URL
 * round trip are written once instead of once per medium behind an `if`.
 *
 * Nothing here touches React, the DOM or the network.
 */

import { formatChapterNumber } from "@/features/novels/book";
import {
  BOOKMARK_MEDIA_MANGA,
  BOOKMARK_MEDIA_NOVEL,
  type Bookmark,
  type BookmarkAnchor,
  type BookmarkMediaType,
} from "./types";

/** A fraction forced into 0.0–1.0. Garbage and NaN read as 0. */
export function clampFraction(value: number | null | undefined): number {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return 0;
  return Math.min(1, Math.max(0, number));
}

/** `media_type` off the wire, defaulted rather than trusted blindly. */
export function bookmarkMediaType(value: string | null | undefined): BookmarkMediaType {
  return value === BOOKMARK_MEDIA_NOVEL ? BOOKMARK_MEDIA_NOVEL : BOOKMARK_MEDIA_MANGA;
}

/** The anchor a stored bookmark describes. */
export function bookmarkAnchor(bookmark: Bookmark): BookmarkAnchor {
  return {
    mediaType: bookmarkMediaType(bookmark.media_type),
    index: Math.max(1, Math.round(bookmark.anchor_index)),
    fraction: clampFraction(bookmark.anchor_fraction),
    total: Math.max(0, Math.round(bookmark.anchor_total)),
  };
}

/**
 * How far through the CHAPTER an anchor sits, or null when that is unknowable.
 *
 * A deliberate mirror of `bookmark_service.position_fraction`, kept in step
 * with it including the `null` (not 0.0) for an unknown unit count: a bookmark
 * migrated from the page-only schema recorded no total, and "0% of the
 * chapter" would be a fabrication. Used for a locally captured anchor, which
 * has no server answer yet; a listed bookmark carries the server's own.
 */
export function anchorPositionFraction(anchor: BookmarkAnchor): number | null {
  if (anchor.total <= 0) return null;
  const index = Math.min(Math.max(1, anchor.index), anchor.total);
  const raw = (index - 1 + clampFraction(anchor.fraction)) / anchor.total;
  return Math.round(Math.min(1, Math.max(0, raw)) * 10_000) / 10_000;
}

/** An anchor resolved against what the chapter actually holds right now. */
export interface ResolvedAnchor {
  /** 1-based index, clamped into range. */
  index: number;
  fraction: number;
  /** The recorded index no longer exists; this is the nearest that does. */
  stale: boolean;
}

/**
 * Degrade honestly (design §3).
 *
 * A source can re-list a chapter with fewer pages, or an aggregator can
 * re-split a wall of text into different paragraphs. When the recorded index
 * is past the end, the nearest valid position is the LAST unit — and at the
 * end of it, because that is the nearest point to where the reader actually
 * was. Clamping upwards (an index below 1, which should not happen but is
 * cheap to survive) lands at the start of the first unit for the mirror-image
 * reason.
 *
 * `total <= 0` means the caller has not measured the chapter yet, which is not
 * the same as the anchor being wrong: the index passes through untouched and
 * is not reported stale.
 */
export function resolveAnchor(
  anchor: Pick<BookmarkAnchor, "index" | "fraction">,
  total: number,
): ResolvedAnchor {
  const wanted = Math.max(1, Math.round(anchor.index));
  const fraction = clampFraction(anchor.fraction);
  if (!Number.isFinite(total) || total <= 0) {
    return { index: wanted, fraction, stale: false };
  }
  const units = Math.floor(total);
  if (wanted > units) return { index: units, fraction: 1, stale: true };
  if (anchor.index < 1) return { index: 1, fraction: 0, stale: true };
  return { index: wanted, fraction, stale: false };
}

/**
 * Where a fraction through `[start, end)` falls, in the same coordinates.
 *
 * The restore half of the capture/restore pair below. A zero-height unit
 * (a page still laying out) resolves to its own start rather than NaN.
 */
export function pointWithin(fraction: number, start: number, end: number): number {
  const span = end - start;
  if (!Number.isFinite(span) || span <= 0) return start;
  return start + clampFraction(fraction) * span;
}

/**
 * The capture half: how far through `[start, end)` the point `at` sits.
 *
 * Exactly inverse to {@link pointWithin}, so capturing a position and
 * restoring it lands on the same pixel whenever the unit has not been
 * re-measured in between — which is what "exactly where it left" means.
 */
export function fractionWithin(at: number, start: number, end: number): number {
  const span = end - start;
  if (!Number.isFinite(span) || span <= 0) return 0;
  return clampFraction((at - start) / span);
}

// --- URL round trip --------------------------------------------------------

/**
 * The query parameter carrying the fraction, for both readers.
 *
 * Separate from the index because the two readers already disagree about what
 * their index parameter means: `?page=` is a PAGE in the manga reader and a
 * progress BUCKET in the novel reader (see `features/novels/progress.ts`), and
 * a bookmark's `anchor_index` is a paragraph, which is neither. Overloading
 * `?page=` for novels would resume a 400-paragraph chapter at bucket 400 —
 * clamped to its end, every time.
 */
export const ANCHOR_FRACTION_PARAM = "at";
/** The novel reader's paragraph index. Never `page`, for the reason above. */
export const ANCHOR_PARAGRAPH_PARAM = "para";

/** `{page, at}` for manga, `{para, at}` for novels. */
export function anchorQuery(anchor: BookmarkAnchor): Record<string, string> {
  const indexParam =
    anchor.mediaType === BOOKMARK_MEDIA_NOVEL ? ANCHOR_PARAGRAPH_PARAM : "page";
  return {
    [indexParam]: String(Math.max(1, Math.round(anchor.index))),
    [ANCHOR_FRACTION_PARAM]: String(clampFraction(anchor.fraction)),
  };
}

/**
 * A chapter href with the anchor appended — where tapping a bookmark goes.
 *
 * `base` comes from `useChapterHref`, which already picks the right reader for
 * the source. This only adds the position, and preserves any query string the
 * builder produced rather than assuming there is none.
 */
export function withAnchorQuery(base: string, anchor: BookmarkAnchor): string {
  const [path, existing = ""] = base.split("?", 2);
  const params = new URLSearchParams(existing);
  for (const [key, value] of Object.entries(anchorQuery(anchor))) {
    params.set(key, value);
  }
  return `${path}?${params.toString()}`;
}

/**
 * One `?index=&at=` pair read back off a route, or null when the route names
 * no anchor.
 *
 * Returns null rather than a default so a plain chapter link is not mistaken
 * for a bookmark opening at unit 1 — the two want different resume behaviour
 * (see the readers' restore effects), and only an explicit index means "go
 * exactly here".
 */
export function parseAnchorParams(
  index: string | number | null | undefined,
  fraction: string | number | null | undefined,
): { index: number; fraction: number } | null {
  const parsedIndex = Number(index);
  if (!Number.isFinite(parsedIndex) || parsedIndex < 1) return null;
  const parsedFraction = Number(fraction);
  return {
    index: Math.floor(parsedIndex),
    fraction: Number.isFinite(parsedFraction) ? clampFraction(parsedFraction) : 0,
  };
}

// --- Labels ----------------------------------------------------------------

/** "Chapter 14", "Chapter 14.5", or the opaque key when there is no number. */
export function bookmarkChapterLabel(bookmark: Bookmark): string {
  if (bookmark.chapter_number == null) return bookmark.chapter_key;
  const ordinal = formatChapterNumber(bookmark.chapter_number);
  return ordinal ? `Chapter ${ordinal}` : bookmark.chapter_key;
}

/**
 * The position indicator the Bookmarks screen prints (design §5).
 *
 * "62% in" whenever the capturing client recorded a unit count, because that
 * is what lets someone choose between two bookmarks in the same chapter
 * without opening either. Without a count it names the unit instead — "Page 7"
 * / "Paragraph 118" — which is honest about knowing where but not how far,
 * rather than inventing a percentage from a total the row does not have.
 */
export function bookmarkPositionLabel(bookmark: Bookmark): string {
  if (bookmark.position_fraction != null) {
    return `${Math.round(bookmark.position_fraction * 100)}% in`;
  }
  return bookmarkMediaType(bookmark.media_type) === BOOKMARK_MEDIA_NOVEL
    ? `Paragraph ${Math.max(1, bookmark.anchor_index)}`
    : `Page ${Math.max(1, bookmark.anchor_index)}`;
}

/** The series line: its title when the series is followed, else its key. */
export function bookmarkSeriesLabel(bookmark: Bookmark): string {
  return bookmark.series_title?.trim() || bookmark.series_key;
}
