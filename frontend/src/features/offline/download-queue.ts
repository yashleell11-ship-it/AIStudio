import { formatBytes } from "./format";
import { readingOrder, type SelectableChapter } from "./chapter-selection";

/**
 * Running a multi-chapter download, one chapter at a time.
 *
 * ONE AT A TIME IS THE POINT. `saveChapterOffline` resolves as soon as the
 * worker has *accepted* the job — `sw.js` replies `{ accepted: true }` and only
 * then starts fetching — so firing ten of them in a loop would put ten chapters
 * in flight at once, each already fetching `SAVE_CONCURRENCY` (4) images in
 * parallel. Forty simultaneous scrapes at a source that a single reader is
 * politely allowed to read is how an instance gets rate-limited. So the queue
 * waits for each chapter to actually settle before starting the next, and
 * settling is observed through the worker's own broadcast state rather than the
 * reply, because the reply says nothing about the outcome.
 *
 * NOTHING HERE BYPASSES A GUARD. Each chapter still goes through the same
 * `mm-offline/save-chapter` message the reader's single-chapter button sends,
 * so the quota reserve, the eviction rules and the "never delete an unread
 * chapter" floor apply exactly as they already do. The only thing bulk adds is
 * order and a tally.
 */

export type SaveOutcome =
  /** Every page stored. */
  | "saved"
  /** Stored with holes — some pages failed. */
  | "incomplete"
  /** The worker stopped for room. Nothing after this can succeed either. */
  | "paused"
  /** Never got as far as storing anything (no manifest, no worker, no answer). */
  | "failed";

export interface DownloadProgress {
  /** Chapters finished, whatever the outcome. */
  completed: number;
  total: number;
  /** The key being worked on, or null between chapters. */
  current: string | null;
}

export interface DownloadRun {
  requested: number;
  saved: number;
  incomplete: number;
  failed: number;
  /** Never started: the run stopped before reaching them. */
  skipped: number;
  /**
   * The run stopped because the browser is out of room for downloads. Not an
   * error — the guard doing its job — but the reader has to be told, because a
   * "download" that silently stored nothing is the worst outcome this feature
   * has.
   */
  outOfSpace: boolean;
  cancelled: boolean;
}

export interface DownloadQueueDeps {
  /**
   * Store one chapter and resolve with what actually happened to it. The
   * implementation dispatches to the service worker and watches its published
   * state; see `use-series-downloads.ts`.
   */
  save: (key: string) => Promise<SaveOutcome>;
  /**
   * Warm what is about to be saved, in one round trip.
   *
   * Called before each chapter with everything still to come, current one
   * first, so the implementation can pull a WINDOW rather than a chapter:
   * `POST /reader/chapters/manifest` and `POST /novels/chapters` both exist and
   * both spend the `bulk` rate-limit bucket once, where twenty single GETs
   * spend the `sources` bucket twenty times and trip it — leaving the reader a
   * 429 on the chapter they actually opened.
   *
   * Every implementation skips what is already in hand, so the calls after a
   * window lands cost nothing and the stride falls out on its own. Best-effort:
   * a chapter the warm missed is still fetched by the worker on its own.
   */
  prepare?: (upcoming: readonly string[]) => Promise<void>;
  onProgress?: (progress: DownloadProgress) => void;
  /** Aborting stops before the NEXT chapter; the one in flight finishes. */
  signal?: AbortSignal;
}

/**
 * The chapters a run should actually contain, in reading order.
 *
 * Selected-but-already-saved chapters are dropped rather than re-fetched: the
 * worker would skip every page it already holds anyway, but a run that reports
 * "10 chapters" and does nothing for six of them is a run that looks broken.
 */
export function planDownload(
  chapters: readonly SelectableChapter[],
  selected: ReadonlySet<string>,
): string[] {
  return readingOrder(chapters)
    .filter((chapter) => selected.has(chapter.key) && !chapter.saved)
    .map((chapter) => chapter.key);
}

export async function runDownloadQueue(
  keys: readonly string[],
  deps: DownloadQueueDeps,
): Promise<DownloadRun> {
  const run: DownloadRun = {
    requested: keys.length,
    saved: 0,
    incomplete: 0,
    failed: 0,
    skipped: 0,
    outOfSpace: false,
    cancelled: false,
  };

  for (let index = 0; index < keys.length; index += 1) {
    if (deps.signal?.aborted) {
      run.cancelled = true;
      run.skipped = keys.length - index;
      return run;
    }
    const key = keys[index];
    deps.onProgress?.({ completed: index, total: keys.length, current: key });

    if (deps.prepare) {
      try {
        await deps.prepare(keys.slice(index));
      } catch {
        // Warming is an optimisation. A window that failed costs a round trip,
        // not a chapter: the save below still fetches what it needs.
      }
    }

    let outcome: SaveOutcome;
    try {
      outcome = await deps.save(key);
    } catch {
      outcome = "failed";
    }

    if (outcome === "paused") {
      // The device is full. Every remaining chapter would pause the same way,
      // so stopping here is the difference between one honest message and
      // twenty identical ones.
      run.outOfSpace = true;
      run.skipped = keys.length - index - 1;
      deps.onProgress?.({ completed: index + 1, total: keys.length, current: null });
      return run;
    }

    if (outcome === "saved") run.saved += 1;
    else if (outcome === "incomplete") run.incomplete += 1;
    else run.failed += 1;

    deps.onProgress?.({ completed: index + 1, total: keys.length, current: null });
  }

  return run;
}

export type RunTone = "ready" | "warn";

export interface RunSummary {
  label: string;
  tone: RunTone;
}

/**
 * What to tell the reader when a run ends.
 *
 * Written so the failure modes cannot hide behind the successes: a run that
 * saved six of ten and ran out of room says both numbers, and says which one
 * stopped it. `freeBytes` is threaded through only when the browser reports a
 * quota — most do, Safari's is a guess, and a made-up number here would be
 * worse than none.
 */
export function describeRun(run: DownloadRun, freeBytes: number | null): RunSummary {
  if (run.requested === 0) {
    return { label: "Nothing to download — those chapters are already saved.", tone: "ready" };
  }

  // Only whole chapters are ever reported as downloaded. A chapter with holes
  // is counted separately however the run ended, because "6 downloaded" when
  // two of the six are missing pages is the lie this feature can least afford.
  const parts = [`${run.saved} of ${run.requested} downloaded`];
  if (run.incomplete > 0) parts.push(`${run.incomplete} with missing pages`);
  if (run.failed > 0) parts.push(`${run.failed} failed`);

  if (run.outOfSpace) {
    parts.push(`${run.skipped} not started`);
    const room = freeBytes !== null ? ` Only ${formatBytes(freeBytes)} is free.` : "";
    return {
      tone: "warn",
      label:
        `Out of room. ${parts.join(", ")}.${room} ` +
        "Remove some downloads and run it again.",
    };
  }

  if (run.cancelled) {
    parts.push(`${run.skipped} not started`);
    return { tone: "warn", label: `Stopped. ${parts.join(", ")}.` };
  }

  if (run.failed > 0 || run.incomplete > 0) {
    return { label: `${parts.join(", ")}.`, tone: "warn" };
  }

  return {
    tone: "ready",
    label: `${run.saved} ${run.saved === 1 ? "chapter" : "chapters"} downloaded.`,
  };
}
