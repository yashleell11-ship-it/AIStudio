/**
 * "Where was I?" — the one rule every client answers it with.
 *
 * Three surfaces used to answer this question three different ways for the same
 * account: the web series page took the FIRST unfinished chapter, the Flutter
 * series page took the LAST one and fell back to chapter 1, and the home strip
 * takes the most recently read. Finishing chapter 40 on the phone and closing
 * the reader on its last page offered chapter 1 next; skimming chapter 5 and
 * jumping ahead pinned the web to chapter 5 forever.
 *
 * The rule below is FURTHEST-WINS, which is the same principle the server's
 * progress merge already runs on:
 *
 *   1. the HIGHEST-numbered chapter with an unfinished progress row — you are
 *      furthest along there, and any earlier unfinished chapter was skimmed or
 *      abandoned deliberately;
 *   2. else the LOWEST-numbered chapter with no progress row at all — the first
 *      thing never opened, which is what "continue" means once every chapter
 *      you have touched is finished;
 *   3. else the last chapter — everything is read, so offer the end rather than
 *      sending a caught-up reader back to the beginning.
 *
 * Pure and free of React so the web can test it and the Flutter port can be
 * checked against the same table of cases.
 */

/** The progress overlay a chapter may carry. Structural, so any row shape fits. */
export interface ResumeProgress {
  last_page: number;
  is_completed: boolean;
}

/** A chapter as the rule needs it: an identity, and an order to sort by. */
export interface ResumeChapter {
  key: string;
  number: number | null;
}

export interface ResumeTarget<T extends ResumeChapter> {
  chapter: T;
  /** The page to open at — the stored position, or 1 for an unread chapter. */
  page: number;
}

/**
 * Ascending chapter order.
 *
 * An unnumbered chapter sorts BEFORE every numbered one and keeps its position
 * relative to its unnumbered siblings, so a source that numbers nothing still
 * produces the listing order it was served in rather than an arbitrary one.
 */
export function compareChapters(a: ResumeChapter, b: ResumeChapter): number {
  const an = a.number ?? Number.NEGATIVE_INFINITY;
  const bn = b.number ?? Number.NEGATIVE_INFINITY;
  return an - bn;
}

/**
 * The chapter "Continue" opens, or null when the series has no chapters.
 *
 * `progress` is keyed by chapter key; a chapter absent from it has never been
 * opened. See the module docstring for the rule and why it is this one.
 */
export function resumeTarget<T extends ResumeChapter>(
  chapters: readonly T[],
  progress: Readonly<Record<string, ResumeProgress | undefined>>,
): ResumeTarget<T> | null {
  const ascending = [...chapters].sort(compareChapters);
  if (ascending.length === 0) return null;

  for (let index = ascending.length - 1; index >= 0; index -= 1) {
    const chapter = ascending[index];
    const row = progress[chapter.key];
    if (row != null && !row.is_completed) {
      return { chapter, page: row.last_page > 0 ? row.last_page : 1 };
    }
  }

  const firstUnread = ascending.find((chapter) => progress[chapter.key] == null);
  return { chapter: firstUnread ?? ascending[ascending.length - 1], page: 1 };
}

/**
 * Whether the button should say "Continue" rather than "Start reading".
 *
 * Asked of the whole series, not of the resolved target: a reader who finished
 * chapter 1 and is being offered chapter 2 is continuing, even though chapter 2
 * has no row of its own. Reading the target's row instead is how the phone came
 * to label a completed chapter 1 "Continue" while offering it as if unfinished.
 */
export function hasStartedReading(
  progress: Readonly<Record<string, ResumeProgress | undefined>>,
): boolean {
  return Object.values(progress).some((row) => row != null);
}
