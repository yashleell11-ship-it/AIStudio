"use client";

import { useCallback, useSyncExternalStore } from "react";

export interface FullscreenController {
  active: boolean;
  supported: boolean;
  enter: () => void;
  exit: () => void;
  toggle: () => void;
}

function subscribe(onChange: () => void): () => void {
  document.addEventListener("fullscreenchange", onChange);
  return () => document.removeEventListener("fullscreenchange", onChange);
}

const isFullscreen = () => document.fullscreenElement != null;
const isSupported = () => document.fullscreenEnabled === true;
const notOnServer = () => false;

/**
 * Fullscreen for the whole document rather than the reader element: the reader
 * chrome is `position: fixed`, and fixed children of a fullscreen element are
 * positioned against that element instead of the viewport, which would strand
 * the controls off-screen.
 *
 * Read through `useSyncExternalStore` so the browser stays the single source of
 * truth — Escape and the browser's own fullscreen affordances bypass this hook
 * entirely, and a mirrored piece of state would drift out of sync with them.
 */
export function useFullscreen(): FullscreenController {
  const active = useSyncExternalStore(subscribe, isFullscreen, notOnServer);
  const supported = useSyncExternalStore(subscribe, isSupported, notOnServer);

  const enter = useCallback(() => {
    if (document.fullscreenElement != null) return;
    // Rejects when the browser refuses the request (no user gesture, policy).
    document.documentElement.requestFullscreen().catch(() => {});
  }, []);

  const exit = useCallback(() => {
    if (document.fullscreenElement == null) return;
    document.exitFullscreen().catch(() => {});
  }, []);

  const toggle = useCallback(() => {
    if (document.fullscreenElement != null) {
      exit();
    } else {
      enter();
    }
  }, [enter, exit]);

  return { active, supported, enter, exit, toggle };
}
