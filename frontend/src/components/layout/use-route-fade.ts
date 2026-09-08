"use client";

import { useEffect } from "react";

import { isImmersivePath } from "@/lib/reader-route";

/** The class `globals.css` hangs the `route-in` animation on. */
export const ROUTE_FADE_CLASS = "route-in";

/**
 * Whether a route change to `pathname` should cross-fade the page.
 *
 * Everything except the two readers. Inside a reader a "route change" is
 * usually the next chapter, and dimming the page you are reading every time
 * the strip crosses a chapter boundary would be the single most irritating
 * animation in the app. The readers already have their own page-transition
 * keyframes for the part of that motion which is wanted.
 */
export function shouldFadeRoute(pathname: string): boolean {
  return !isImmersivePath(pathname);
}

/**
 * Cross-fades the app's scroller when the route under it changes.
 *
 * Applied to `<main>` itself rather than a wrapper element, and in opacity
 * only. `main` is the app's only scroller, so a transform on it would make it
 * the containing block for any fixed descendant, and a wrapper would put a new
 * block box between it and every page that assumes it is a direct child.
 *
 * The class is removed and re-added around a forced layout read because that
 * is what restarts a running CSS animation; re-rendering with the same class
 * does nothing. Keying the element by pathname would restart it declaratively
 * but would also remount the scroller, losing scroll position and, on a route
 * whose component does not change, everything the page had in hand.
 */
export function useRouteFade(
  container: HTMLElement | null,
  pathname: string,
): void {
  useEffect(() => {
    if (!container || !shouldFadeRoute(pathname)) return;

    container.classList.remove(ROUTE_FADE_CLASS);
    // Forces the removal to land before the class goes back on. Without this
    // the browser coalesces both mutations and the animation never restarts.
    void container.offsetWidth;
    container.classList.add(ROUTE_FADE_CLASS);

    return () => container.classList.remove(ROUTE_FADE_CLASS);
  }, [container, pathname]);
}
