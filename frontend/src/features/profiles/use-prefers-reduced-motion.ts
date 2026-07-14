"use client";

import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function getSnapshot(): boolean {
  return window.matchMedia(QUERY).matches;
}

/** SSR-safe: assume motion is allowed until the client can read the query. */
function getServerSnapshot(): boolean {
  return false;
}

/**
 * Whether the viewer has asked the OS to reduce motion. Components use this to
 * drop entrance/selection transforms and jump straight to end states, in
 * addition to the global CSS `prefers-reduced-motion` guard in globals.css.
 */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
