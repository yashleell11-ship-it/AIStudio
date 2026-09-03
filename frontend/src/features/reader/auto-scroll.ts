/**
 * Continuous auto-scroll for the vertical/continuous reading mode — the "big
 * one" for webtoons, where thumbing through a 200-panel strip is miserable.
 *
 * This module is pure, mirroring how `cinema.ts` is factored: the play/pause
 * state machine, the px/second -> per-frame-distance rate maths, the speed
 * clamp, and the self-scroll/external-scroll test all live here with no DOM
 * access. `use-auto-scroll.ts` drives it with a real `requestAnimationFrame`
 * loop and the reader's actual scroll container.
 *
 * Rate maths are elapsed-time based (px/second * seconds-since-last-frame),
 * not a fixed per-tick pixel step, so the strip covers the same distance in
 * the same wall-clock time whether the browser is painting at 60Hz, 120Hz, or
 * has just dropped a few frames — no drift, no dependency on frame rate.
 */

/** User-facing speed levels, 1 (slowest) to 10 (fastest). */
export const MIN_AUTO_SCROLL_SPEED = 1;
export const MAX_AUTO_SCROLL_SPEED = 10;
export const DEFAULT_AUTO_SCROLL_SPEED = 5;

/** Rate range the 1-10 levels map onto, in CSS pixels per second. */
const MIN_RATE_PX_PER_S = 20;
const MAX_RATE_PX_PER_S = 220;

/**
 * A single very long animation-frame gap (tab backgrounded, a heavy layout,
 * the debugger paused) must not be repaid as one huge jump the instant the
 * loop resumes — that reads as a stutter/teleport, not smooth scrolling. Any
 * gap longer than this is treated as if it were exactly this long.
 */
export const MAX_FRAME_DELTA_MS = 100;

export function clampAutoScrollSpeed(speed: number): number {
  if (!Number.isFinite(speed)) return DEFAULT_AUTO_SCROLL_SPEED;
  return Math.min(
    MAX_AUTO_SCROLL_SPEED,
    Math.max(MIN_AUTO_SCROLL_SPEED, Math.round(speed)),
  );
}

/** Convert a 1-10 speed level into a scroll rate in pixels per second. */
export function autoScrollPxPerSecond(speed: number): number {
  const level = clampAutoScrollSpeed(speed);
  const ratio = (level - MIN_AUTO_SCROLL_SPEED) / (MAX_AUTO_SCROLL_SPEED - MIN_AUTO_SCROLL_SPEED);
  return MIN_RATE_PX_PER_S + ratio * (MAX_RATE_PX_PER_S - MIN_RATE_PX_PER_S);
}

/**
 * How far to move the scroll container on one animation frame, given the rate
 * and the time elapsed since the previous frame. `deltaMs` is clamped so a
 * long gap between frames cannot produce a sudden jump.
 */
export function autoScrollFrameDistance(pxPerSecond: number, deltaMs: number): number {
  if (!(pxPerSecond > 0) || !(deltaMs > 0)) return 0;
  const clampedDelta = Math.min(deltaMs, MAX_FRAME_DELTA_MS);
  return (pxPerSecond * clampedDelta) / 1000;
}

/**
 * Did the scroll container move somewhere the auto-scroll loop did not put
 * it? The loop tracks the `scrollTop` it last wrote (post-clamp, so it
 * matches whatever the browser actually settled on); a later `scroll` event
 * reporting a different position means a wheel, touch drag, keyboard turn or
 * scrollbar drag moved it instead — the reader taking control back.
 */
export function isExternalScroll(
  actualScrollTop: number,
  expectedScrollTop: number,
  epsilonPx = 0.5,
): boolean {
  return Math.abs(actualScrollTop - expectedScrollTop) > epsilonPx;
}

export interface AutoScrollState {
  playing: boolean;
}

export const INITIAL_AUTO_SCROLL_STATE: AutoScrollState = { playing: false };

export type AutoScrollEvent =
  /** Play/pause control or keyboard shortcut. */
  | { type: "toggle" }
  /** Explicit start (never invoked automatically — see `use-auto-scroll.ts`). */
  | { type: "play" }
  /** Explicit stop (control, shortcut, or leaving continuous mode). */
  | { type: "pause" }
  /** A manual scroll, wheel, drag or page-turn the loop did not cause itself. */
  | { type: "interaction" }
  /** The strip reached its bottom edge while playing. */
  | { type: "end-of-chapter" };

/**
 * Advance the play/pause machine. `interaction` and `end-of-chapter` are
 * named separately from `pause` even though they resolve the same way, so
 * call sites and tests can say *why* playback stopped rather than collapsing
 * every stop into one anonymous event.
 */
export function autoScrollReduce(
  state: AutoScrollState,
  event: AutoScrollEvent,
): AutoScrollState {
  switch (event.type) {
    case "toggle":
      return { playing: !state.playing };
    case "play":
      return state.playing ? state : { playing: true };
    case "pause":
    case "interaction":
    case "end-of-chapter":
      return state.playing ? { playing: false } : state;
    default:
      return state;
  }
}
