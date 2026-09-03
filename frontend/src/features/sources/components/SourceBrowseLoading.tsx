"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { seriesCoverUrl } from "@/features/library/api";
import { useContinueReading } from "@/features/library/hooks";
import { usePrefersReducedMotion } from "@/features/profiles/use-prefers-reduced-motion";
import { cn } from "@/lib/cn";
import {
  COVERS_PER_SLIDE,
  LOADING_TIPS,
  buildCarouselSlides,
  nextSlideIndex,
  sourceHue,
} from "../loading-carousel";
import { SourceLogo } from "./SourceLogo";

interface SourceBrowseLoadingProps {
  /** True while the browse request is still in flight. */
  active: boolean;
  sourceId: string;
  sourceName: string;
  iconUrl?: string | null;
}

/** How long each carousel frame stays before cross-fading to the next. */
const ROTATE_MS = 3500;
/** Cross-fade duration for the whole overlay leaving once browse resolves. */
const FADE_MS = 500;
/** Delay before we admit the source is being slow. */
const LONG_HINT_MS = 3000;
/** How many recent reads to pull for the carousel. */
const HISTORY_LIMIT = 9;

/**
 * Animated "Latest reads" loading state shown over the source catalog while
 * `GET /sources/{id}/browse` is slow. Purely decorative: nothing here is
 * clickable and it never navigates. It self-manages its exit — once `active`
 * flips false (browse resolved with success OR error) it cross-fades itself
 * out and unmounts, revealing the real catalog underneath.
 */
export function SourceBrowseLoading({
  active,
  sourceId,
  sourceName,
  iconUrl,
}: SourceBrowseLoadingProps) {
  const reducedMotion = usePrefersReducedMotion();
  // Fetched in parallel the moment this mounts (first render, alongside the
  // browse request) — it never gates or delays browse.
  const history = useContinueReading(HISTORY_LIMIT);

  const [slideIndex, setSlideIndex] = useState(0);
  const [showLongHint, setShowLongHint] = useState(false);
  const [rendered, setRendered] = useState(active);
  const [leaving, setLeaving] = useState(false);
  const [prevActive, setPrevActive] = useState(active);

  const historyItems = history.data;
  const slides = useMemo(
    () => buildCarouselSlides(historyItems ?? [], COVERS_PER_SLIDE),
    [historyItems],
  );
  const hasHistory = slides.length > 0;
  const rotationCount = hasHistory ? slides.length : LOADING_TIPS.length;

  // React to browse starting/resolving during render (React's recommended
  // pattern for prop-derived state — avoids a setState-in-effect). A fresh load
  // re-arms the overlay; a resolved load begins the cross-fade exit, or (for
  // reduced motion) unmounts immediately with no animation.
  if (active !== prevActive) {
    setPrevActive(active);
    if (active) {
      setRendered(true);
      setLeaving(false);
    } else if (reducedMotion) {
      setRendered(false);
    } else {
      setLeaving(true);
    }
  }

  // Unmount once the cross-fade has played out. The setState lives in the timer
  // callback (async), not the effect body.
  useEffect(() => {
    if (!leaving) {
      return;
    }
    const timer = window.setTimeout(() => setRendered(false), FADE_MS);
    return () => window.clearTimeout(timer);
  }, [leaving]);

  // Auto-rotate covers / tips. Disabled for reduced motion (static frame),
  // while leaving, or when there is nothing to rotate through.
  useEffect(() => {
    if (reducedMotion || leaving || rotationCount <= 1) {
      return;
    }
    const id = window.setInterval(() => {
      setSlideIndex((current) => nextSlideIndex(current, rotationCount));
    }, ROTATE_MS);
    return () => window.clearInterval(id);
  }, [reducedMotion, leaving, rotationCount]);

  // Admit slowness after a beat.
  useEffect(() => {
    if (!active) {
      return;
    }
    const timer = window.setTimeout(() => setShowLongHint(true), LONG_HINT_MS);
    return () => window.clearTimeout(timer);
  }, [active]);

  if (!rendered) {
    return null;
  }

  const hue = sourceHue(sourceId);
  const activeTip = LOADING_TIPS[slideIndex % LOADING_TIPS.length];

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-start overflow-hidden rounded-3xl bg-surface px-4 pt-8 transition-opacity duration-500",
        leaving ? "opacity-0" : "opacity-100",
      )}
    >
      {/* Muted source-colour wash, brought in once the source proves slow. */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 transition-opacity duration-700"
        style={{
          backgroundImage: `radial-gradient(120% 90% at 50% -10%, hsl(${hue} 70% 55% / 0.14), transparent 70%)`,
          opacity: showLongHint ? 1 : 0,
        }}
      />

      <SourceLogo
        id={sourceId}
        name={sourceName}
        iconUrl={iconUrl}
        size={56}
        className="border-border/80 shadow-sm"
      />
      <p className="mt-3 flex items-center gap-1 text-sm font-medium text-fg">
        Opening {sourceName}
        <span aria-hidden className="inline-flex gap-0.5">
          <span className="h-1 w-1 animate-pulse rounded-full bg-primary [animation-delay:0ms]" />
          <span className="h-1 w-1 animate-pulse rounded-full bg-primary [animation-delay:150ms]" />
          <span className="h-1 w-1 animate-pulse rounded-full bg-primary [animation-delay:300ms]" />
        </span>
      </p>
      <p className="mt-1 text-xs text-muted">
        {showLongHint ? "This source can take ~10s." : "Fetching catalog…"}
      </p>

      {/* Carousel / fallback */}
      <div className="relative mt-5 h-[220px] w-full max-w-xl sm:h-[260px]">
        {hasHistory
          ? slides.map((slide, index) => (
              <div
                key={index}
                aria-hidden
                className={cn(
                  "absolute inset-0 grid grid-cols-3 gap-4 transition-opacity duration-700",
                  index === slideIndex % slides.length ? "opacity-100" : "opacity-0",
                )}
              >
                {slide.map((item) => (
                  <div
                    key={`${item.source_id}:${item.series_key}`}
                    className="relative aspect-[2/3] overflow-hidden rounded-2xl border border-border bg-surface-2"
                  >
                    <Image
                      src={seriesCoverUrl({ sourceId: item.source_id, seriesKey: item.series_key })}
                      alt=""
                      fill
                      className="object-cover"
                      sizes="160px"
                      unoptimized
                    />
                  </div>
                ))}
              </div>
            ))
          : (
            <div className="flex h-full flex-col items-center justify-between">
              <div className="grid w-full grid-cols-3 gap-4">
                {Array.from({ length: COVERS_PER_SLIDE }).map((_, index) => (
                  <div
                    key={index}
                    aria-hidden
                    className="aspect-[2/3] animate-pulse rounded-2xl bg-surface-2"
                  />
                ))}
              </div>
              <p className="mt-4 min-h-[2.5rem] px-4 text-center text-sm text-muted">
                {activeTip}
              </p>
            </div>
          )}
      </div>
    </div>
  );
}
