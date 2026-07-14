"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import { usePrefersReducedMotion } from "./use-prefers-reduced-motion";

export interface ScrollMarqueeProps {
  images: string[];
  className?: string;
  /**
   * Optional scroll ancestor to track instead of the window — e.g. an app-shell
   * inner scroll container that owns the page scroll. Backward compatible: omit
   * (or pass `null`) to track window scroll as before.
   */
  scrollContainer?: HTMLElement | null;
}

function Row({ images, transform }: { images: string[]; transform: string }) {
  return (
    <div
      className="flex w-max gap-6"
      style={{ transform, willChange: "transform" }}
    >
      {images.map((src, index) => (
        // Fixed-size decorative marquee tiles per the design contract; next/image
        // is unsuitable for the free-scrolling transform track.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={`${src}-${index}`}
          src={src}
          alt=""
          loading="lazy"
          width={420}
          height={270}
          className="h-[270px] w-[420px] rounded-2xl object-cover"
        />
      ))}
    </div>
  );
}

/**
 * Dual-row image marquee driven by page scroll: the two rows drift in opposite
 * directions as the section passes through the viewport. Images are tripled for
 * a seamless loop. Honors reduced motion by rendering static, clipped rows.
 */
export function ScrollMarquee({
  images,
  className,
  scrollContainer,
}: ScrollMarqueeProps) {
  const reducedMotion = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [offset, setOffset] = useState(0);

  // Triple the array so the row stays filled while it slides.
  const looped = useMemo(() => [...images, ...images, ...images], [images]);

  useEffect(() => {
    if (reducedMotion) return;

    const target: HTMLElement | Window = scrollContainer ?? window;

    const handleScroll = () => {
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      // Parallax based on how far the section top sits above the scroll
      // viewport bottom. For the window this is the original
      // `(scrollY - sectionTop + innerHeight) * 0.3`, simplified to
      // `(innerHeight - rect.top) * 0.3`; for a container we measure relative
      // to the container's own viewport instead.
      if (scrollContainer) {
        const cRect = scrollContainer.getBoundingClientRect();
        setOffset((cRect.height - (rect.top - cRect.top)) * 0.3);
      } else {
        setOffset((window.innerHeight - rect.top) * 0.3);
      }
    };

    target.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => target.removeEventListener("scroll", handleScroll);
  }, [reducedMotion, scrollContainer]);

  const shift = offset - 200;

  return (
    <div ref={ref} className={cn("flex flex-col gap-6 overflow-hidden", className)}>
      <Row
        images={looped}
        transform={reducedMotion ? "none" : `translateX(${shift}px)`}
      />
      <Row
        images={looped}
        transform={reducedMotion ? "none" : `translateX(${-shift}px)`}
      />
    </div>
  );
}

export default ScrollMarquee;
