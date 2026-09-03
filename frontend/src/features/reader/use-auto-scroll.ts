"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { usePrefersReducedMotion } from "@/components/premium/use-prefers-reduced-motion";
import { autoScrollFrameDistance, autoScrollReduce, INITIAL_AUTO_SCROLL_STATE, isExternalScroll } from "./auto-scroll";
import { advanceReaderScroll } from "./scroll-preparation";

export interface AutoScrollController {
  /** The rAF loop is actively driving the scroll container. */
  playing: boolean;
  /** `prefers-reduced-motion` — surfaced so the control can explain itself,
   * never used to hide it: auto-scroll is offered either way, just never
   * started automatically. */
  reducedMotion: boolean;
  toggle: () => void;
  pause: () => void;
}

interface UseAutoScrollInput {
  /** The reader's own scroll container. `null` while it is not mounted yet. */
  scrollElement: HTMLElement | null;
  /**
   * Continuous mode, chapter loaded, no error — auto-scroll only ever drives
   * the vertical strip. Turning this false (mode switch, navigating away)
   * pauses playback rather than leaving a loop running against a container
   * nobody can see.
   */
  active: boolean;
  /** The strip has reached its bottom edge (mirrors `ChapterReader`'s own
   * `atBottom`, not recomputed here — see the module doc in `auto-scroll.ts`). */
  atBottom: boolean;
  /** Px/second scroll rate, already resolved from the per-series speed level
   * via `autoScrollPxPerSecond` — the hook only runs the loop, it does not
   * own the speed setting. */
  pxPerSecond: number;
}

/**
 * Drives the {@link autoScrollReduce} play/pause machine with a real
 * `requestAnimationFrame` loop against the reader's scroll container.
 *
 * Never starts itself: `playing` begins `false` on every mount (a chapter
 * change remounts `ChapterReader` entirely, so this is also what resets
 * playback at a chapter boundary — see the "stop, don't roll into the next
 * chapter" decision in `ChapterReader`). Nothing here reads a persisted
 * "was playing" flag, which is what keeps this honest under
 * `prefers-reduced-motion`: the control stays available, it just never fires
 * on its own.
 */
export function useAutoScroll({
  scrollElement,
  active,
  atBottom,
  pxPerSecond,
}: UseAutoScrollInput): AutoScrollController {
  const reducedMotion = usePrefersReducedMotion();
  const [state, dispatch] = useReducer(autoScrollReduce, INITIAL_AUTO_SCROLL_STATE);

  const pxPerSecondRef = useRef(pxPerSecond);
  useEffect(() => {
    pxPerSecondRef.current = pxPerSecond;
  }, [pxPerSecond]);

  // The scrollTop the loop itself last wrote (read back post-clamp). A later
  // `scroll` event landing anywhere else means something other than this loop
  // moved the container — see `isExternalScroll`.
  const expectedScrollTopRef = useRef<number | null>(null);

  // Drive (or stop driving) the loop as play state, container or mode change.
  // The frame-to-frame recursion lives entirely inside this effect (a plain
  // local function, not a memoized callback) so each frame always closes over
  // the `element` this specific effect run captured, with no risk of it
  // outliving a container swap or racing a later run's own loop.
  useEffect(() => {
    if (!state.playing || !scrollElement || !active) {
      return;
    }
    const element = scrollElement;
    let frame = 0;
    let lastTimestamp: number | null = null;
    expectedScrollTopRef.current = element.scrollTop;

    const step = (timestamp: number) => {
      const last = lastTimestamp;
      lastTimestamp = timestamp;
      if (last != null) {
        const distance = autoScrollFrameDistance(pxPerSecondRef.current, timestamp - last);
        if (distance > 0) {
          expectedScrollTopRef.current = advanceReaderScroll(element, distance);
        }
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);

    return () => cancelAnimationFrame(frame);
  }, [state.playing, scrollElement, active]);

  // Any scroll the loop did not itself produce — wheel, touch drag, a
  // keyboard page turn, dragging the scrollbar — hands control straight back.
  useEffect(() => {
    if (!scrollElement || !state.playing) return;
    const handleScroll = () => {
      const expected = expectedScrollTopRef.current;
      if (expected != null && !isExternalScroll(scrollElement.scrollTop, expected)) {
        return;
      }
      dispatch({ type: "interaction" });
    };
    scrollElement.addEventListener("scroll", handleScroll, { passive: true });
    return () => scrollElement.removeEventListener("scroll", handleScroll);
  }, [scrollElement, state.playing]);

  // Auto-pause at the end of the chapter (spec: stop rather than roll into a
  // seamless next chapter — see `ChapterReader`).
  useEffect(() => {
    if (!state.playing || !atBottom) return;
    dispatch({ type: "end-of-chapter" });
  }, [state.playing, atBottom]);

  // Leaving continuous mode (or the chapter finishing loading out from under
  // it) pauses rather than leaving a silent loop nobody can stop.
  useEffect(() => {
    if (!active) dispatch({ type: "pause" });
  }, [active]);

  const toggle = useCallback(() => dispatch({ type: "toggle" }), []);
  const pause = useCallback(() => dispatch({ type: "pause" }), []);

  return useMemo(
    () => ({ playing: state.playing, reducedMotion, toggle, pause }),
    [state.playing, reducedMotion, toggle, pause],
  );
}
