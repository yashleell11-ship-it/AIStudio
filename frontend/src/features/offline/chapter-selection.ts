import {
  EMPTY_SELECTION,
  extendSelection,
  selectAll,
  toggleSelection,
  type SelectionState,
} from "@/features/library/selection";

/**
 * Choosing which chapters to download.
 *
 * The shift-click math is the library grid's, generic over the id
 * (`features/library/selection.ts`); what lives here is the part that is about
 * chapters specifically — the range helpers. The owner's ask was "multi
 * download back so i can download 10 chapters in 1 go", and ticking ten
 * checkboxes by hand is the thing being replaced, not the thing being built.
 *
 * Every helper works in READING order, never display order. A series page sorts
 * newest-first by default, so "the next 10" taken off the top of the list would
 * be the ten most recent chapters — the opposite of what a reader forty
 * chapters in is asking for.
 */

export type ChapterSelection = SelectionState<string>;

export const EMPTY_CHAPTER_SELECTION: ChapterSelection = EMPTY_SELECTION;

/** One row, as the helpers below need to see it. */
export interface SelectableChapter {
  key: string;
  /** Source-reported chapter number; null when the source did not give one. */
  number: number | null;
  /** Already on the device and complete — nothing to download. */
  saved: boolean;
  /** Finished, per the server's progress rows. */
  read: boolean;
}

/**
 * Reading order: numbered chapters ascending, unnumbered ones last in the order
 * the source listed them. The same rule the series pages use to pick "start
 * from the beginning", so "next 10" and that button agree about which way is
 * forwards.
 */
export function readingOrder(
  chapters: readonly SelectableChapter[],
): SelectableChapter[] {
  return [...chapters].sort((a, b) => {
    if (a.number == null && b.number == null) return 0;
    if (a.number == null) return 1;
    if (b.number == null) return -1;
    return a.number - b.number;
  });
}

/**
 * The next `count` chapters worth downloading, starting where the reader is.
 *
 * "Where the reader is" is the first chapter they have not finished; already
 * saved chapters are skipped rather than counted, because a reader asking for
 * ten more means ten they do not have. A fully caught-up series yields nothing,
 * which is honest — there is nothing ahead to take.
 */
export function nextChapters(
  chapters: readonly SelectableChapter[],
  count: number,
): string[] {
  if (!(count > 0)) return [];
  const ordered = readingOrder(chapters);
  const start = ordered.findIndex((chapter) => !chapter.read);
  const from = start === -1 ? ordered.length : start;
  const out: string[] = [];
  for (let index = from; index < ordered.length && out.length < count; index += 1) {
    if (!ordered[index].saved) out.push(ordered[index].key);
  }
  return out;
}

/** Everything not finished and not already on the device, in reading order. */
export function unreadChapters(chapters: readonly SelectableChapter[]): string[] {
  return readingOrder(chapters)
    .filter((chapter) => !chapter.read && !chapter.saved)
    .map((chapter) => chapter.key);
}

/**
 * The whole series, minus what is already saved — the owner's "download whole
 * series for novels too". Offered for prose, where a chapter is a few kilobytes
 * of text; a 300-chapter manga is gigabytes of page images and gets the bounded
 * helpers instead.
 */
export function everyChapter(chapters: readonly SelectableChapter[]): string[] {
  return readingOrder(chapters)
    .filter((chapter) => !chapter.saved)
    .map((chapter) => chapter.key);
}

/** Add a set of keys to what is already ticked, leaving the anchor alone. */
export function addChapters(
  state: ChapterSelection,
  keys: readonly string[],
): ChapterSelection {
  if (keys.length === 0) return state;
  const ids = new Set(state.ids);
  for (const key of keys) ids.add(key);
  return { ids, anchor: state.anchor ?? keys[0] };
}

export {
  extendSelection as extendChapterSelection,
  selectAll as selectAllChapters,
  toggleSelection as toggleChapter,
};
