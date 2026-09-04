"use client";

import Image from "next/image";
import Link from "next/link";
import { Play } from "lucide-react";
import { useChapterHref } from "@/features/novels/use-chapter-href";
import { seriesCoverUrl } from "../api";
import {
  continueReadingChapterLabel,
  continueReadingKey,
  continueReadingPercent,
  continueReadingRef,
  resolveSeriesTitle,
} from "../continue-reading";
import { useFollowedIndex } from "../hooks";
import type { ContinueReadingItem } from "../types";

interface ContinueReadingProps {
  items: ContinueReadingItem[];
  isLoading?: boolean;
  /**
   * True when the rail is showing novels, which have no pages: their stored
   * position is a progress bucket, so it reads back as a percentage.
   */
  novels?: boolean;
}

/**
 * The "pick up where you left off" section on the library landing.
 *
 * Fed by `GET /library/continue-reading` (most recent unfinished chapter per
 * `(source_id, series_key)`). The lead item renders as a large hero card; the
 * rest follow in the horizontal rail. Covers come from the source proxy; the
 * resume link drops straight onto the last page read. The payload has no series
 * title, so it is joined from the followed-series index (falls back to the key).
 */
export function ContinueReading({ items, isLoading, novels }: ContinueReadingProps) {
  const { titles } = useFollowedIndex();
  // Resolves to whichever reader the row's source calls for.
  const chapterHref = useChapterHref();

  if (isLoading) {
    return (
      <section className="mb-8" aria-busy="true" aria-label="Loading continue reading">
        <div className="mb-3 h-4 w-40 animate-pulse rounded bg-surface-2" />
        <div className="mb-4 h-[220px] w-full animate-pulse rounded-3xl bg-surface-2 sm:h-[260px]" />
        <div className="flex gap-4 overflow-hidden">
          {Array.from({ length: 4 }).map((_, index) => (
            <div
              key={index}
              className="h-[120px] w-[280px] shrink-0 animate-pulse rounded-2xl bg-surface-2"
            />
          ))}
        </div>
      </section>
    );
  }

  if (items.length === 0) {
    return null;
  }

  const [hero, ...rest] = items;
  const heroPercent = continueReadingPercent(hero);

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
        Continue Reading
      </h2>

      <Link
        href={chapterHref(continueReadingRef(hero), hero.last_page)}
        className="group mb-4 block focus-visible:outline-none"
      >
        <article className="glass-card relative flex gap-4 overflow-hidden rounded-3xl p-3 transition-colors group-hover:border-primary/40 group-focus-visible:border-primary/60 sm:gap-6 sm:p-4">
          <div className="relative aspect-[2/3] w-28 shrink-0 overflow-hidden rounded-2xl bg-surface-2 sm:w-40 md:w-44">
            <Image
              src={seriesCoverUrl(continueReadingRef(hero))}
              alt={resolveSeriesTitle(hero, titles)}
              fill
              className="object-cover"
              sizes="(max-width: 640px) 112px, 176px"
              unoptimized
            />
            <div className="absolute inset-0 flex items-center justify-center bg-void/40 opacity-0 transition-opacity group-hover:opacity-100">
              <Play className="size-8 fill-white text-white" aria-hidden />
            </div>
          </div>

          <div className="flex min-w-0 flex-1 flex-col justify-center gap-2 py-1 pr-1 sm:gap-3">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-primary">
              Jump back in
            </p>
            <h3 className="line-clamp-2 text-lg font-semibold text-fg sm:text-2xl">
              {resolveSeriesTitle(hero, titles)}
            </h3>
            <p className="text-sm text-muted">
              {continueReadingChapterLabel(hero)} &middot;{" "}
              {novels
                ? `${heroPercent}% in`
                : `page ${hero.last_page}${hero.page_count > 0 ? ` of ${hero.page_count}` : ""}`}
            </p>
            <div className="mt-1 max-w-sm">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${heroPercent}%` }}
                />
              </div>
              {heroPercent > 0 ? (
                <p className="mt-1 text-[11px] tabular-nums text-muted">
                  {heroPercent}% through this chapter
                </p>
              ) : null}
            </div>
          </div>
        </article>
      </Link>

      {rest.length > 0 ? (
        <div className="flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth pb-2">
          {rest.map((item) => {
            const percent = continueReadingPercent(item);
            return (
              <Link
                key={continueReadingKey(item)}
                href={chapterHref(continueReadingRef(item), item.last_page)}
                className="group w-[280px] shrink-0 snap-start"
              >
                <article className="glass-card flex h-full gap-3 overflow-hidden rounded-2xl p-2 transition-colors hover:border-primary/40">
                  <div className="relative h-[104px] w-[70px] shrink-0 overflow-hidden rounded-lg bg-surface-2">
                    <Image
                      src={seriesCoverUrl(continueReadingRef(item))}
                      alt={resolveSeriesTitle(item, titles)}
                      fill
                      className="object-cover"
                      sizes="70px"
                      unoptimized
                    />
                    <div className="absolute inset-0 flex items-center justify-center bg-void/40 opacity-0 transition-opacity group-hover:opacity-100">
                      <Play className="size-6 fill-white text-white" aria-hidden />
                    </div>
                  </div>

                  <div className="flex min-w-0 flex-1 flex-col justify-between py-1 pr-1">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-fg">
                        {resolveSeriesTitle(item, titles)}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-muted">
                        {continueReadingChapterLabel(item)}
                      </p>
                    </div>

                    <div>
                      <div className="flex items-center justify-between text-[11px] text-muted">
                        <span>{novels ? "In progress" : `Page ${item.last_page}`}</span>
                        {percent > 0 ? (
                          <span className="tabular-nums text-primary">{percent}%</span>
                        ) : null}
                      </div>
                      <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-white/10">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </article>
              </Link>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
