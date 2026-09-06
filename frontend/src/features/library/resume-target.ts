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
 *   1. the HIGHEST-numbered chapter with ANY progress row decides — you are
 *      furthest along there, and any earlier chapter, unfinished or untouched,
 *      was skimmed or skipped deliberately;
 *   2. if that chapter is unfinished, resume in it at the stored page;
 *   3. if it is finished, the chapter after it at page 1 — which is what
 *      "continue" means once the furthest thing you touched is done;
 *   4. else the last chapter — everything is read, so offer the end rather than
 *      sending a caught-up reader back to the beginning.
 *
 * Rule 1 looks at ANY row, not the highest UNFINISHED one, and the difference
 * is a rewind. The phone's continuous feed completes a chapter only when its
 * last page settles, so chapters scrolled through keep mid-chapter rows; a rule
 * that skipped finished chapters then offered the newest of those rows the
 * moment the chapter actually being read was finished — chapter 4 page 11
 * after finishing chapter 7.
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
    if (row == null) continue;
    if (!row.is_completed) {
      return { chapter, page: row.last_page > 0 ? row.last_page : 1 };
    }
    // The furthest chapter touched is finished: continue is the one after it,
    // or the end of the series when nothing comes after it.
    return { chapter: ascending[index + 1] ?? ascending[ascending.length - 1], page: 1 };
  }

  return { chapter: ascending[0], page: 1 };
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
