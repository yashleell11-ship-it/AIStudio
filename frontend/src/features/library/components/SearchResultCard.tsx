"use client";

import Image from "next/image";
import Link from "next/link";
import { Star } from "lucide-react";
import { coverUrl } from "@/features/library/api";
import type { SeriesSummary } from "@/features/library/types";

interface SearchResultCardProps {
  series: SeriesSummary;
}

function languageLabel(language: string): string {
  switch (language.toLowerCase()) {
    case "ko":
      return "Manhwa";
    case "ja":
      return "Manga";
    case "zh":
      return "Manhua";
    case "en":
      return "Webtoon";
    default:
      return language.toUpperCase();
  }
}

function readerHref(series: SeriesSummary): string | null {
  if (series.chapter_count === 0) {
    return null;
  }
  return `/library/${series.id}`;
}

export function SearchResultCard({ series }: SearchResultCardProps) {
  const href = readerHref(series);
  const progress = series.reading_progress;

  const content = (
    <article className="glass-card group flex gap-4 rounded-xl p-3 transition-all hover:border-violet-500/30 hover:shadow-glow">
      <div className="relative h-[120px] w-[80px] shrink-0 overflow-hidden rounded-lg bg-surface-2">
        <Image
          src={coverUrl(series.id)}
          alt={series.title}
          fill
          className="object-cover transition-transform duration-300 group-hover:scale-105"
          sizes="80px"
          unoptimized
        />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-start justify-between gap-3">
          <h3 className="line-clamp-1 text-base font-semibold text-fg group-hover:text-violet-400">
            {series.title}
          </h3>
          {progress != null ? (
            <div className="flex shrink-0 items-center gap-1 text-xs text-amber-400">
              <Star className="size-3 fill-amber-400" aria-hidden />
              <span className="tabular-nums">{Math.round(progress.progress_pct)}%</span>
            </div>
          ) : series.is_favorite ? (
            <div className="flex shrink-0 items-center gap-1 text-xs text-amber-400">
              <Star className="size-3 fill-amber-400" aria-hidden />
              <span>Fav</span>
            </div>
          ) : null}
        </div>

        {series.author ? (
          <p className="mt-0.5 truncate text-sm text-muted">{series.author}</p>
        ) : null}

        {series.description ? (
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted/80">
            {series.description}
          </p>
        ) : (
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted/60">
            {series.chapter_count} chapters · {series.page_count.toLocaleString()} pages
          </p>
        )}

        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-3">
          <div className="flex flex-wrap gap-1.5">
            {series.reading_status ? (
              <span className="rounded-md bg-white/5 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted">
                {series.reading_status.replace(/_/g, " ")}
              </span>
            ) : null}
          </div>
          <span className="text-[10px] font-medium uppercase tracking-wide text-violet-400/70">
            {languageLabel(series.language)}
          </span>
        </div>
      </div>
    </article>
  );

  if (!href) {
    return content;
  }

  return <Link href={href}>{content}</Link>;
}

export function SearchResultCardSkeleton() {
  return (
    <div className="glass-card flex gap-4 rounded-xl p-3">
      <div className="h-[120px] w-[80px] shrink-0 animate-pulse rounded-lg bg-surface-2" />
      <div className="flex flex-1 flex-col gap-2 py-1">
        <div className="h-5 w-2/3 animate-pulse rounded bg-surface-2" />
        <div className="h-4 w-1/3 animate-pulse rounded bg-surface-2" />
        <div className="h-10 w-full animate-pulse rounded bg-surface-2" />
        <div className="mt-auto h-4 w-1/4 animate-pulse rounded bg-surface-2" />
      </div>
    </div>
  );
}
