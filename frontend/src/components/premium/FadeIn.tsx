"use client";

import { useMemo, type ElementType, type ReactNode } from "react";
import { motion } from "framer-motion";

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
 * Scroll-triggered entrance: fades and slides children into place once, when
 * they enter the viewport.
 *
 * Both the duration AND the travel distance scale with the active design
 * preset, which is what makes the motion axis felt rather than merely faster:
 * Cinema's content drifts a few pixels over a fifth of a second, Signature's
 * arrives from 30px over seven tenths. A scale of 0 — which is what
 * `prefers-reduced-motion` resolves to — renders fully visible with no
 * transform and no motion component at all.
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

  const MotionComponent = useMemo(
    () => (as ? motion.create(as as ElementType) : motion.div),
    [as],
  ) as typeof motion.div;

  if (motionScale === 0) {
    const StaticComponent = (as ?? "div") as ElementType;
    return <StaticComponent className={className}>{children}</StaticComponent>;
  }

  return (
    <MotionComponent
      className={cn(className)}
      initial={{ opacity: 0, x: x * motionScale, y: y * motionScale }}
      whileInView={{ opacity: 1, x: 0, y: 0 }}
      viewport={{ once: true, margin: "50px", amount: 0 }}
      transition={{
        duration: FULL_DURATION * motionScale,
        delay: delay * motionScale,
        ease: [0.25, 0.1, 0.25, 1],
      }}
    >
      {children}
    </MotionComponent>
  );
}

export default FadeIn;
