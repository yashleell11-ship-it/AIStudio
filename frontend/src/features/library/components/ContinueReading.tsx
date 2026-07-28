"use client";

import Image from "next/image";
import Link from "next/link";
import { Play } from "lucide-react";
import { coverUrl } from "../api";
import type { ContinueReadingItem } from "../types";

interface ContinueReadingProps {
  items: ContinueReadingItem[];
  isLoading?: boolean;
}

/**
 * The "pick up where you left off" rail on the library landing.
 *
 * Fed by `GET /library/continue-reading`
 * (backend/services/library_service.py:896-937), which is already 18+-gated the
 * same way the grid is — a series hidden from the shelf must not reappear here,
 * where its cover is the largest thing on screen.
 *
 * Covers come from `coverUrl()` rather than the payload's `cover_url`: the
 * backend hands back a backend-relative path (`/library/covers/{id}`,
 * utils/mobile_urls.py:4-5) for the mobile client, and the web client has to
 * prefix its own API base.
 */
export function ContinueReading({ items, isLoading }: ContinueReadingProps) {
  if (isLoading) {
    return (
      <section className="mb-8" aria-busy="true" aria-label="Loading continue reading">
        <div className="mb-3 h-4 w-40 animate-pulse rounded bg-surface-2" />
        <div className="flex gap-4 overflow-hidden">
          {Array.from({ length: 5 }).map((_, index) => (
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

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
        Continue Reading
      </h2>
      <div className="flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth pb-2">
        {items.map((item) => (
          <Link
            key={`${item.series_id}:${item.chapter_id}`}
            href={`/reader/${item.series_id}/${item.chapter_id}?page=${item.last_page}`}
            className="group w-[280px] shrink-0 snap-start"
          >
            <article className="glass-card flex h-full gap-3 overflow-hidden rounded-2xl p-2 transition-colors hover:border-primary/40">
              <div className="relative h-[104px] w-[70px] shrink-0 overflow-hidden rounded-lg bg-surface-2">
                <Image
                  src={coverUrl(item.series_id)}
                  alt={item.series_title}
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
                    {item.series_title}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {item.chapter_title}
                  </p>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] text-muted">
                    <span>Page {item.last_page}</span>
                    <span className="tabular-nums text-primary">
                      {Math.round(item.progress_pct)}%
                    </span>
                  </div>
                  <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{
                        width: `${Math.min(100, Math.max(0, item.progress_pct))}%`,
                      }}
                    />
                  </div>
                </div>
              </div>
            </article>
          </Link>
        ))}
      </div>
    </section>
  );
}
