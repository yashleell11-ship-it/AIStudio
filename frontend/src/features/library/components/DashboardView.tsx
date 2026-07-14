"use client";

import { useMemo } from "react";
import { coverUrl } from "@/features/library/api";
import { useContinueReading, useSeriesList } from "@/features/library/hooks";
import { useScrollContainer } from "@/lib/scroll-container";
import { ApiError } from "@/types/api";
import { AboutSection } from "./home/AboutSection";
import { ContinueStack } from "./home/ContinueStack";
import { ExploreSection } from "./home/ExploreSection";
import { HeroSection } from "./home/HeroSection";
import { MarqueeSection } from "./home/MarqueeSection";

const MARQUEE_LENGTH = 21;

/**
 * The home experience: a cinematic, full-page scroll built from the premium
 * primitives. Hero → cover marquee → About → light Explore contrast → dark
 * sticky "Continue" stack. Motion primitives track the app-shell's inner scroll
 * container (the app never scrolls at the window level) via `useScrollContainer`.
 */
export function DashboardView() {
  const scrollContainer = useScrollContainer();

  const continueQuery = useContinueReading(12);
  const trendingQuery = useSeriesList({ page: 1, per_page: 12, sort: "recent" });
  const recentQuery = useSeriesList({ page: 1, per_page: 12, sort: "updated" });

  const continueItems = useMemo(
    () => continueQuery.data ?? [],
    [continueQuery.data],
  );
  const trending = useMemo(
    () => trendingQuery.data?.items ?? [],
    [trendingQuery.data],
  );
  const recent = useMemo(
    () => recentQuery.data?.items ?? [],
    [recentQuery.data],
  );

  const firstContinue = continueItems[0];
  const continueHref = firstContinue
    ? `/reader/${firstContinue.series_id}/${firstContinue.chapter_id}?page=${firstContinue.last_page}`
    : null;

  // Unique cover set from every list, then repeated to fill a full marquee row.
  const marqueeImages = useMemo(() => {
    const ids: number[] = [];
    const push = (id: number) => {
      if (!ids.includes(id)) ids.push(id);
    };
    continueItems.forEach((item) => push(item.series_id));
    trending.forEach((s) => push(s.id));
    recent.forEach((s) => push(s.id));

    if (ids.length === 0) return [];

    const urls = ids.map(coverUrl);
    const out: string[] = [];
    while (out.length < MARQUEE_LENGTH) out.push(...urls);
    return out.slice(0, MARQUEE_LENGTH);
  }, [continueItems, trending, recent]);

  const error =
    continueQuery.error instanceof ApiError
      ? continueQuery.error.message
      : trendingQuery.error instanceof ApiError
        ? trendingQuery.error.message
        : recentQuery.error instanceof ApiError
          ? recentQuery.error.message
          : null;

  const cardsLoading =
    continueQuery.isLoading || trendingQuery.isLoading || recentQuery.isLoading;

  return (
    <div className="relative bg-bg">
      {error ? (
        <div className="px-6 pt-4 md:px-10">
          <div className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {error}
          </div>
        </div>
      ) : null}

      <HeroSection firstContinue={firstContinue} continueHref={continueHref} />

      <MarqueeSection images={marqueeImages} scrollContainer={scrollContainer} />

      <AboutSection />

      <ExploreSection />

      <ContinueStack
        continueItems={continueItems}
        trending={trending}
        recent={recent}
        loading={cardsLoading}
        scrollContainer={scrollContainer}
      />
    </div>
  );
}
