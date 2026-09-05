"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * How long the reader has been reading, as the progress endpoint wants it.
 *
 * `POST /reader/progress` takes `time_spent_seconds` as the wall-clock time
 * spent SINCE THIS CLIENT'S LAST PUSH, not a running total — the server
 * accumulates it onto the chapter's row and turns each advance's delta into a
 * `ReadingSession`'s duration (`progress_service.py`). A cumulative figure
 * would be re-added on every push.
 *
 * No client was sending it at all, so every session was recorded with
 * `started_at == ended_at` and every duration derived from them was zero. The
 * statistics screen's "Time read" was therefore not merely wrong, it was
 * structurally incapable of being anything but 0 — while pages and streaks
 * carried on working, so the screen looked alive.
 */

/**
 * The longest gap between two pushes that is still counted as reading.
 *
 * The reader pushes on a 500 ms debounce whenever the position advances, so a
 * gap of minutes means nobody was reading — a locked screen, another tab, a
 * chapter left open overnight. Counting the cap rather than the gap keeps a
 * genuinely slow page honest and refuses to bill an idle night as reading. It
 * errs low on purpose: an under-count is a smaller lie than nine hours of
 * "reading" a locked phone.
 */
export const MAX_PUSH_SECONDS = 300;

/** Whole seconds between two instants, floored at 0 and capped at `cap`. */
export function elapsedSince(
  lastAt: number | null,
  now: number,
  cap: number = MAX_PUSH_SECONDS,
): number {
  if (lastAt === null || !Number.isFinite(lastAt) || !Number.isFinite(now)) return 0;
  // A clock that jumped backwards (NTP correction, a device waking) reports
  // nothing rather than a negative the server would clamp away anyway.
  const seconds = Math.floor((now - lastAt) / 1000);
  if (seconds <= 0) return 0;
  return Math.min(seconds, cap);
}

/**
 * `take()` — the seconds read since the last time it was asked, and reset.
 *
 * One clock per reader rather than one per chapter: the time between two
 * pushes was spent reading whatever the push being made is about, including
 * the chapter just finished at a seam. Attributing it any more finely would
 * need to know when the reading line crossed, which is exactly the number the
 * push is reporting.
 */
export function useReadingClock(): () => number {
  const lastAt = useRef<number | null>(null);

  // Started at mount, so the first push carries the time spent on the first
  // page instead of zero.
  useEffect(() => {
    lastAt.current = Date.now();
  }, []);

  return useCallback(() => {
    const now = Date.now();
    const seconds = elapsedSince(lastAt.current, now);
    lastAt.current = now;
    return seconds;
  }, []);
}
