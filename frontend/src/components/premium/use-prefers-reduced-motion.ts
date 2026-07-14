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
 * Shared reduced-motion hook for the premium motion primitives. Returns `true`
 * when the viewer has asked the OS to reduce motion; every primitive in this
 * folder uses it to drop transforms and jump straight to end states.
 *
 * SSR-safe via `useSyncExternalStore` (assumes motion allowed until hydrated).
 */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
