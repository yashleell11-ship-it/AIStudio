"use client";

import Link from "next/link";
import { FadeIn } from "@/components/premium/FadeIn";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { StickyStack } from "@/components/premium/StickyStack";
import { coverUrl } from "@/features/library/api";
import type {
  ContinueReadingItem,
  SeriesSummary,
} from "@/features/library/types";

interface CoverEntry {
  id: number;
  href: string;
  title: string;
}

export interface ContinueStackProps {
  continueItems: ContinueReadingItem[];
  trending: SeriesSummary[];
  recent: SeriesSummary[];
  loading: boolean;
  /** Scroll ancestor that owns the page scroll (app-shell inner container). */
  scrollContainer: HTMLElement | null;
}

function CoverGrid({ entries }: { entries: CoverEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="mt-6 text-sm text-muted">Nothing here yet.</p>
    );
  }
  return (
    <div className="mt-6 grid grid-cols-4 gap-3 sm:grid-cols-6">
      {entries.slice(0, 6).map((entry) => (
        <Link key={`${entry.id}-${entry.href}`} href={entry.href} className="group">
          {/* Cookie-authed covers resolve via a raw <img> on web. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={coverUrl(entry.id)}
            alt={entry.title}
            className="aspect-[2/3] w-full rounded-xl object-cover ring-1 ring-border transition group-hover:ring-primary"
          />
        </Link>
      ))}
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="mt-6 grid grid-cols-4 gap-3 sm:grid-cols-6">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="aspect-[2/3] w-full animate-pulse rounded-xl bg-surface-2"
        />
      ))}
    </div>
  );
}

function StackCard({
  title,
  subtitle,
  entries,
  loading,
}: {
  title: string;
  subtitle: string;
  entries: CoverEntry[];
  loading: boolean;
}) {
  return (
    <div className="p-6 md:p-10">
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="font-display text-2xl font-bold text-fg md:text-3xl">
          {title}
        </h3>
        <span className="shrink-0 text-xs uppercase tracking-widest text-muted">
          {subtitle}
        </span>
      </div>
      {loading ? <SkeletonGrid /> : <CoverGrid entries={entries} />}
    </div>
  );
}

const seriesEntry = (s: SeriesSummary): CoverEntry => ({
  id: s.id,
  href: `/library/${s.id}`,
  title: s.title,
});

/**
 * Dark, layered close to the home page: three warm-bordered cards that pin and
 * scale as the section scrolls, each surfacing a slice of the reader's world.
 */
export function ContinueStack({
  continueItems,
  trending,
  recent,
  loading,
  scrollContainer,
}: ContinueStackProps) {
  const continueEntries: CoverEntry[] = continueItems.map((item) => ({
    id: item.series_id,
    href: `/reader/${item.series_id}/${item.chapter_id}?page=${item.last_page}`,
    title: item.series_title,
  }));

  const cards = [
    <StackCard
      key="continue"
      title="Continue Reading"
      subtitle="Pick up where you left off"
      entries={continueEntries}
      loading={loading}
    />,
    <StackCard
      key="trending"
      title="Trending Now"
      subtitle="What's moving"
      entries={trending.map(seriesEntry)}
      loading={loading}
    />,
    <StackCard
      key="updates"
      title="Recent Updates"
      subtitle="Fresh chapters"
      entries={recent.map(seriesEntry)}
      loading={loading}
    />,
  ];

  return (
    <section className="relative -mt-10 rounded-t-[40px] bg-bg px-6 pb-24 pt-24 sm:rounded-t-[50px] md:rounded-t-[60px] md:px-10">
      <div className="mx-auto max-w-5xl">
        <FadeIn>
          <HeroHeading as="h2">Continue</HeroHeading>
        </FadeIn>
        <StickyStack
          // Remount when the scroll container resolves so framer-motion binds it.
          key={scrollContainer ? "scoped" : "window"}
          scrollContainer={scrollContainer}
          className="mt-12"
          cardClassName="overflow-hidden border border-border"
        >
          {cards}
        </StickyStack>
      </div>
    </section>
  );
}
