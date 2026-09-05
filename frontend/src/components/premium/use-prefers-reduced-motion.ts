"use client";

import { useSyncExternalStore } from "react";
import { usePresetMotion } from "@/features/preferences/preset-store";

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

/**
 * How much the JS-driven motion primitives should actually move: 0 (not at
 * all) to 1 (as designed).
 *
 * Two inputs, one number. The viewer's OS setting is absolute and wins outright
 * — `prefers-reduced-motion` is an accessibility request, not a preference to
 * be blended — and below that, the active design preset scales everything: Matte
 * and Editorial trim the entrance animations, Cinema cuts them to a third
 * because an interface you are looking through should not be moving.
 *
 * The CSS half of the same decision is `--shape-motion`, which the app's own
 * keyframes multiply their durations by. Framer-motion animates through React
 * state and cannot read a custom property, so it reads the number here instead;
 * `preset.test.ts` pins the two to the same value.
 */
export function useMotionScale(): number {
  const reduced = usePrefersReducedMotion();
  const preset = usePresetMotion();
  return reduced ? 0 : preset;
}
