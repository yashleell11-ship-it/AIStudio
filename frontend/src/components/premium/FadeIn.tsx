"use client";

import {
  useCallback,
  useState,
  type CSSProperties,
  type ElementType,
  type ReactNode,
} from "react";

import { cn } from "@/lib/cn";
import { useMotionScale } from "./use-prefers-reduced-motion";

export interface FadeInProps {
  children: ReactNode;
  /** Render as a different element/component (default `div`). */
  as?: ElementType;
  /** Entrance delay in seconds. */
  delay?: number;
  /** Horizontal travel distance in px (default 0). */
  x?: number;
  /** Vertical travel distance in px (default 30). */
  y?: number;
  className?: string;
}

/** How long the entrance runs at full motion, in seconds. */
const FULL_DURATION = 0.7;

/**
 * How far outside the viewport an element starts its entrance. Kept at the
 * `viewport={{ margin: "50px" }}` this component used to pass framer-motion, so
 * content still begins arriving just before it is scrolled to rather than
 * visibly popping at the edge.
 */
const ROOT_MARGIN = "50px";

/**
 * Scroll-triggered entrance: fades and slides children into place once, when
 * they enter the viewport.
 *
 * Both the duration AND the travel distance scale with the active design
 * preset, which is what makes the motion axis felt rather than merely faster:
 * Cinema's content drifts a few pixels over a fifth of a second, Signature's
 * arrives from 30px over seven tenths. A scale of 0 — which is what
 * `prefers-reduced-motion` resolves to — renders fully visible with no
 * transform and no observer at all.
 *
 * Plain `IntersectionObserver` and a CSS transition, not a motion library. This
 * was the only live framer-motion consumer left in the app (`AnimatedText`,
 * `StickyStack`, `ScrollMarquee` and `Magnet` have no importers), and because
 * five routes reach it the bundler hoisted the whole of framer-motion into the
 * chunk EVERY route loads — 39 KB gzipped, carried by the reader too, to fade
 * some headings in. The animation here is a two-property transition with a
 * fixed easing; it never needed an animation engine, and on a phone the
 * download was the expensive part.
 */
export function FadeIn({
  children,
  as,
  delay = 0,
  x = 0,
  y = 30,
  className,
}: FadeInProps) {
  const motionScale = useMotionScale();
  const [entered, setEntered] = useState(false);

  /**
   * Observation is attached through the ref callback rather than an effect: the
   * node is what is being watched, so it is the node's arrival that should
   * start watching it, and a conditionally-rendered child never leaves a
   * stale observer behind.
   */
  const observe = useCallback((node: HTMLElement | null) => {
    if (!node) return;
    if (typeof IntersectionObserver === "undefined") {
      // No observer (very old browser, or a test environment): show the
      // content rather than leaving it invisible forever.
      setEntered(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        // `amount: 0` — any part of it counts as arrived.
        if (entries.some((entry) => entry.isIntersecting)) {
          setEntered(true);
          // `once`: the entrance never replays, so stop watching immediately.
          observer.disconnect();
        }
      },
      { rootMargin: ROOT_MARGIN },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const Component = (as ?? "div") as ElementType;

  if (motionScale === 0) {
    return <Component className={className}>{children}</Component>;
  }

  const style: CSSProperties = entered
    ? {
        opacity: 1,
        transform: "none",
        transition: `opacity ${FULL_DURATION * motionScale}s cubic-bezier(0.25, 0.1, 0.25, 1) ${delay * motionScale}s, transform ${FULL_DURATION * motionScale}s cubic-bezier(0.25, 0.1, 0.25, 1) ${delay * motionScale}s`,
        willChange: "auto",
      }
    : {
        opacity: 0,
        transform: `translate3d(${x * motionScale}px, ${y * motionScale}px, 0)`,
        willChange: "opacity, transform",
      };

  return (
    <Component ref={observe} className={cn(className)} style={style}>
      {children}
    </Component>
  );
}

export default FadeIn;
