"use client";

import { ScrollMarquee } from "@/components/premium/ScrollMarquee";

export interface MarqueeSectionProps {
  /** Cover URLs to scroll — already padded to a full row by the caller. */
  images: string[];
  /** Scroll ancestor that owns the page scroll (app-shell inner container). */
  scrollContainer: HTMLElement | null;
}

/**
 * Dual-row cover marquee that drifts as the home page scrolls. Renders nothing
 * until there are covers to show.
 */
export function MarqueeSection({ images, scrollContainer }: MarqueeSectionProps) {
  if (images.length === 0) return null;

  return (
    <section className="bg-bg pb-10 pt-24 sm:pt-32 md:pt-40">
      <ScrollMarquee images={images} scrollContainer={scrollContainer} />
    </section>
  );
}
