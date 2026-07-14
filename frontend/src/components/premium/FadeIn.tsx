"use client";

import { useMemo, type ElementType, type ReactNode } from "react";
import { motion } from "framer-motion";

import { cn } from "@/lib/cn";
import { usePrefersReducedMotion } from "./use-prefers-reduced-motion";

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

/**
 * Scroll-triggered entrance: fades and slides children into place once, when
 * they enter the viewport. Honors reduced motion by rendering fully visible
 * with no transform.
 */
export function FadeIn({
  children,
  as,
  delay = 0,
  x = 0,
  y = 30,
  className,
}: FadeInProps) {
  const reducedMotion = usePrefersReducedMotion();

  const MotionComponent = useMemo(
    () => (as ? motion.create(as as ElementType) : motion.div),
    [as],
  ) as typeof motion.div;

  if (reducedMotion) {
    const StaticComponent = (as ?? "div") as ElementType;
    return <StaticComponent className={className}>{children}</StaticComponent>;
  }

  return (
    <MotionComponent
      className={cn(className)}
      initial={{ opacity: 0, x, y }}
      whileInView={{ opacity: 1, x: 0, y: 0 }}
      viewport={{ once: true, margin: "50px", amount: 0 }}
      transition={{ duration: 0.7, delay, ease: [0.25, 0.1, 0.25, 1] }}
    >
      {children}
    </MotionComponent>
  );
}

export default FadeIn;
