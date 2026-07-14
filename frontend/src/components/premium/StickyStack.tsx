"use client";

import { useRef, type ReactNode } from "react";
import { motion, useScroll, useTransform } from "framer-motion";

import { cn } from "@/lib/cn";
import { usePrefersReducedMotion } from "./use-prefers-reduced-motion";

export interface StickyStackProps {
  /** One card per entry; they stack and scale as the section scrolls. */
  children: ReactNode[];
  className?: string;
  /** Extra classes applied to each card wrapper. */
  cardClassName?: string;
  /**
   * Optional scroll ancestor that owns the page scroll — e.g. an app-shell inner
   * scroll container. Backward compatible: omit (or pass `null`) to track window
   * scroll. Because framer-motion binds the container on mount, remount this
   * component (via `key`) when the container resolves from `null` to an element.
   */
  scrollContainer?: HTMLElement | null;
}

interface StickyCardProps {
  index: number;
  total: number;
  progress: ReturnType<typeof useScroll>["scrollYProgress"];
  cardClassName?: string;
  children: ReactNode;
}

function StickyCard({
  index,
  total,
  progress,
  cardClassName,
  children,
}: StickyCardProps) {
  const targetScale = 1 - (total - 1 - index) * 0.03;
  const scale = useTransform(progress, [index / total, 1], [1, targetScale]);

  return (
    <div className="sticky top-24 flex h-[85vh] items-start justify-center md:top-32">
      <motion.div
        style={{ scale, top: index * 28 }}
        className={cn(
          "relative w-full origin-top rounded-3xl bg-surface",
          cardClassName,
        )}
      >
        {children}
      </motion.div>
    </div>
  );
}

/**
 * Generic sticky card stack: as the section scrolls, each card pins near the
 * top and scales down slightly so later cards settle on top of earlier ones.
 * Honors reduced motion by rendering the cards in normal flow, unscaled.
 */
export function StickyStack({
  children,
  className,
  cardClassName,
  scrollContainer,
}: StickyStackProps) {
  const reducedMotion = usePrefersReducedMotion();
  const container = useRef<HTMLDivElement>(null);
  // Captured once at mount; callers remount (via `key`) when the container
  // resolves, so this stays in sync without mutating a ref during render.
  const scrollRef = useRef<HTMLElement | null>(scrollContainer ?? null);
  const total = children.length;

  const { scrollYProgress } = useScroll({
    target: container,
    container: scrollContainer ? scrollRef : undefined,
    offset: ["start start", "end end"],
  });

  if (reducedMotion) {
    return (
      <div className={cn("flex flex-col gap-8", className)}>
        {children.map((card, index) => (
          <div
            key={index}
            className={cn("w-full rounded-3xl bg-surface", cardClassName)}
          >
            {card}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div ref={container} className={cn(className)}>
      {children.map((card, index) => (
        <StickyCard
          key={index}
          index={index}
          total={total}
          progress={scrollYProgress}
          cardClassName={cardClassName}
        >
          {card}
        </StickyCard>
      ))}
    </div>
  );
}

export default StickyStack;
