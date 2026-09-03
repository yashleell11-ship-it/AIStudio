/**
 * "Did they actually stop here?" — a delay between a pointer entering something
 * and the work that hover is supposed to trigger.
 *
 * The source series page prefetches a chapter on `mouseenter`, per row. Moving
 * the pointer from the top of a sixty-chapter list to the bottom enters every
 * row on the way, so one gesture fired sixty prefetches in about a second —
 * enough to spend the whole `/sources/*` rate-limit bucket (60/minute) and make
 * the page's own requests start answering 429, and enough to hammer the
 * upstream source with sixty chapter scrapes nobody asked for.
 *
 * Waiting a beat before acting means a pass-over costs nothing and only the row
 * the pointer settles on is prefetched.
 */

/** Long enough that a sweep across a list settles nothing, short enough to be
 * invisible to someone reaching for a row. */
export const HOVER_PREFETCH_DELAY_MS = 120;

export interface HoverIntent<T> {
  /** The pointer (or focus) arrived on `value`. */
  enter: (value: T) => void;
  /** It left again before the delay elapsed — cancel. */
  leave: () => void;
  /** Drop any pending timer; call on unmount. */
  dispose: () => void;
}

/**
 * `run` is called once, `delayMs` after the last `enter` that was not followed
 * by a `leave`. A second `enter` replaces the first, so sweeping across a list
 * resolves to at most the row the pointer stopped on.
 */
export function createHoverIntent<T>(
  run: (value: T) => void,
  delayMs: number = HOVER_PREFETCH_DELAY_MS,
): HoverIntent<T> {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const cancel = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };

  return {
    enter: (value: T) => {
      cancel();
      timer = setTimeout(() => {
        timer = null;
        run(value);
      }, delayMs);
    },
    leave: cancel,
    dispose: cancel,
  };
}
