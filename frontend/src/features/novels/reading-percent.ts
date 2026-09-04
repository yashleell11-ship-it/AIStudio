/**
 * How far through the chapter the reader is, deliberately kept OUT of React
 * state.
 *
 * The read-out changes on almost every scroll frame. As component state that
 * re-rendered the whole page of prose — hundreds of paragraphs, plus the type
 * panel — for a number displayed by two spans, which is what made scrolling a
 * long chapter feel like it ran at half frame rate. Here the scroll handler
 * writes, and only the two elements that show the number subscribe:
 * `useSyncExternalStore` is exactly this shape.
 *
 * Whole percents, and a notify only when the whole percent actually moves, so
 * the ninety-odd frames of a scroll that do not change the read-out cost
 * nothing. Nothing else in the reader is derived from this: progress saving,
 * resuming and bookmarks all go through the measured paragraph offsets
 * (`progress.ts`, `paragraph-anchor.ts`), which is why this can be a display
 * value and no more.
 */

export interface ReadingPercentStore {
  /** Subscribe to changes; returns the unsubscribe. */
  subscribe: (listener: () => void) => () => void;
  /** The current whole percent — the `useSyncExternalStore` snapshot. */
  get: () => number;
  /** Report a position, as a percentage that need not be whole or in range. */
  set: (percent: number) => void;
}

export function createReadingPercent(initial = 0): ReadingPercentStore {
  let value = initial;
  const listeners = new Set<() => void>();

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    get: () => value,
    set(percent) {
      // A non-finite reading — a zero-height container measured mid-layout —
      // would never compare equal to itself, so it would notify on every
      // single frame and render "NaN%" while doing it.
      if (!Number.isFinite(percent)) return;
      const next = Math.min(Math.max(Math.round(percent), 0), 100);
      if (next === value) return;
      value = next;
      for (const listener of listeners) listener();
    },
  };
}
