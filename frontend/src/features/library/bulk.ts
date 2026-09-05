/**
 * Bounded-concurrency runner for the bulk actions.
 *
 * None of the bulk operations the toolbar offers has a bulk endpoint: favourite
 * and shelf status are `PATCH /library/series/{id}`, unfollow is
 * `DELETE /library/follow/{id}`. Every one of them is therefore N requests, and
 * "select all" on this grid is 200 of them.
 *
 * Firing 200 at once would open 200 sockets against a self-hosted backend that
 * runs the whole library on one SQLite file, and give the user a frozen page
 * with no idea how far along it is. So: a small fixed pool, progress after every
 * item, failures collected instead of aborting the run — a single 404 on one
 * series must not strand the other 199.
 */

/** Small enough to stay polite to a NAS, large enough to beat a serial loop. */
export const BULK_CONCURRENCY = 4;

export interface BulkProgress {
  completed: number;
  failed: number;
  total: number;
}

export interface BulkFailure<T> {
  item: T;
  error: unknown;
}

export interface BulkOutcome<T> {
  total: number;
  succeeded: T[];
  failures: BulkFailure<T>[];
  /** True when the run stopped early because `signal` fired. */
  aborted: boolean;
}

export interface BulkOptions {
  concurrency?: number;
  onProgress?: (progress: BulkProgress) => void;
  /** Aborting stops *starting* new work; requests already in flight finish. */
  signal?: AbortSignal;
}

export async function runBulk<T>(
  items: readonly T[],
  worker: (item: T) => Promise<unknown>,
  options: BulkOptions = {},
): Promise<BulkOutcome<T>> {
  const total = items.length;
  const succeeded: T[] = [];
  const failures: BulkFailure<T>[] = [];
  let aborted = false;

  if (total === 0) {
    return { total, succeeded, failures, aborted };
  }

  // Never more workers than items: an empty worker would still cost a tick, and
  // a caller asking for 0 or -1 should not deadlock the run.
  const requested = options.concurrency ?? BULK_CONCURRENCY;
  const concurrency = Math.max(1, Math.min(Math.floor(requested) || 1, total));

  let cursor = 0;

  const drain = async (): Promise<void> => {
    for (;;) {
      if (options.signal?.aborted) {
        aborted = true;
        return;
      }
      const index = cursor;
      if (index >= total) {
        return;
      }
      cursor += 1;
      const item = items[index];
      try {
        await worker(item);
        succeeded.push(item);
      } catch (error) {
        failures.push({ item, error });
      }
      options.onProgress?.({
        completed: succeeded.length + failures.length,
        failed: failures.length,
        total,
      });
    }
  };

  await Promise.all(Array.from({ length: concurrency }, drain));

  return { total, succeeded, failures, aborted };
}

/**
 * One line of plain English for the toast the bar shows when a run ends.
 *
 * `verb` is the past participle of what happened to a series ("removed",
 * "favourited"), so the sentence reads "12 series removed."
 */
export function summarizeBulkOutcome<T>(
  outcome: BulkOutcome<T>,
  verb: string,
): string {
  const done = outcome.succeeded.length;
  const failed = outcome.failures.length;

  if (done === 0 && failed > 0) {
    return `Nothing ${verb} — all ${failed} failed.`;
  }
  if (outcome.aborted) {
    const skipped = outcome.total - done - failed;
    const tail = failed > 0 ? `, ${failed} failed` : "";
    return `Stopped: ${done} series ${verb}${tail}, ${skipped} skipped.`;
  }
  if (failed > 0) {
    return `${done} series ${verb}, ${failed} failed.`;
  }
  return `${done} series ${verb}.`;
}
