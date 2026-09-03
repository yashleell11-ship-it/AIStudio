"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { usePrefersReducedMotion } from "@/components/premium/use-prefers-reduced-motion";
import {
  CINEMA_IDLE_MS,
  cinemaReduce,
  INITIAL_CINEMA_STATE,
  type CinemaState,
} from "./cinema";

export interface CinemaController {
  /** Cinema mode is engaged (chrome auto-hides). */
  enabled: boolean;
  /** The chrome is currently on screen. */
  chromeVisible: boolean;
  /** Animate transitions, or swap instantly (`prefers-reduced-motion`). */
  reducedMotion: boolean;
  /** Toggle cinema mode (control / keyboard shortcut). */
  toggle: () => void;
  /** Register user activity — reveals the chrome and re-arms the idle timer. */
  notifyActivity: () => void;
}

interface UseCinemaInput {
  /** Persisted per-profile preference: auto-engage cinema mode on open. */
  persistedEnabled: boolean;
  /** The reader scroll container, for the scroll / pointer activity listeners. */
  scrollElement: HTMLElement | null;
  /** False while the reader is still loading — no point arming timers yet. */
  active: boolean;
  /** Called when the toggle flips, so the preference can be persisted. */
  onEnabledChange: (enabled: boolean) => void;
}

/**
 * Drives the cinema-mode {@link cinemaReduce} machine with a real idle timer and
 * pointer / scroll / key activity listeners. Auto-engages ~3 s after the reader
 * settles when the per-profile preference is on; either way, once engaged the
 * chrome hides on idle and returns on any activity.
 */
export function useCinema({
  persistedEnabled,
  scrollElement,
  active,
  onEnabledChange,
}: UseCinemaInput): CinemaController {
  const reducedMotion = usePrefersReducedMotion();
  const [state, dispatch] = useReducer(cinemaReduce, INITIAL_CINEMA_STATE);
  const stateRef = useRef<CinemaState>(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearIdle = useCallback(() => {
    if (idleTimer.current) {
      clearTimeout(idleTimer.current);
      idleTimer.current = null;
    }
  }, []);

  const armIdle = useCallback(() => {
    clearIdle();
    idleTimer.current = setTimeout(() => {
      idleTimer.current = null;
      dispatch({ type: "idle" });
    }, CINEMA_IDLE_MS);
  }, [clearIdle]);

  const notifyActivity = useCallback(() => {
    if (!stateRef.current.enabled) return;
    dispatch({ type: "activity" });
    armIdle();
  }, [armIdle]);

  const toggle = useCallback(() => {
    const next = !stateRef.current.enabled;
    dispatch({ type: "toggle" });
    onEnabledChange(next);
    if (next) armIdle();
    else clearIdle();
  }, [armIdle, clearIdle, onEnabledChange]);

  // Auto-engage from the persisted preference, once the reader has settled.
  const autoEngagedRef = useRef(false);
  useEffect(() => {
    if (!active || autoEngagedRef.current) return;
    autoEngagedRef.current = true;
    if (persistedEnabled) {
      dispatch({ type: "enable" });
      armIdle();
    }
  }, [active, persistedEnabled, armIdle]);

  // Activity listeners. Pointer-move and scroll reveal the chrome; a plain tap
  // is handled by the reader's own toggle, which also calls notifyActivity.
  useEffect(() => {
    if (!active) return;
    const targets: Array<[EventTarget, string]> = [
      [window, "pointermove"],
      [window, "keydown"],
    ];
    if (scrollElement) targets.push([scrollElement, "scroll"]);

    const handler = () => notifyActivity();
    for (const [target, event] of targets) {
      target.addEventListener(event, handler, { passive: true });
    }
    return () => {
      for (const [target, event] of targets) {
        target.removeEventListener(event, handler);
      }
    };
  }, [active, scrollElement, notifyActivity]);

  useEffect(() => clearIdle, [clearIdle]);

  return {
    enabled: state.enabled,
    chromeVisible: !state.enabled || state.chrome === "shown",
    reducedMotion,
    toggle,
    notifyActivity,
  };
}
