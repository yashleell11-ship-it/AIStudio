"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { Star } from "lucide-react";
import { coverUrl } from "@/features/library/api";
import { useToggleFavorite } from "@/features/library/hooks";
import type { SeriesSummary } from "@/features/library/types";
import { cn } from "@/lib/cn";

interface SeriesCardProps {
  series: SeriesSummary;
}

function readerHref(series: SeriesSummary): string | null {
  if (series.chapter_count === 0) {
    return null;
  }
  return `/library/${series.id}`;
}

function languageLabel(language: string): string {
  switch (language.toLowerCase()) {
    case "ko":
      return "manhwa";
    case "ja":
      return "manga";
    case "zh":
      return "manhua";
    case "en":
      return "webtoon";
    default:
      return language.toLowerCase();
  }
}

function statusBadgeStyle(status: string): string {
  switch (status) {
    case "reading":
      return "bg-primary/85 text-primary-fg";
    case "completed":
      return "bg-success/80 text-white";
    case "on_hold":
    case "on-hold":
      return "bg-accent/85 text-white";
    case "plan_to_read":
    case "plan":
      return "bg-white/20 text-white";
    case "unread":
      return "bg-white/15 text-white";
    default:
      return "bg-white/20 text-white";
  }
}

function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function SeriesCardContent({
  series,
  isHovered,
}: {
  series: SeriesSummary;
  isHovered: boolean;
}) {
  const progress = series.reading_progress;
  const toggleFavorite = useToggleFavorite();

  return (
    <article className="group relative overflow-hidden rounded-2xl transition-all duration-300 hover:shadow-glow">
      <div className="relative aspect-[2/3] w-full overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-white/5 transition-all duration-300 group-hover:ring-primary/30">
        <Image
          src={coverUrl(series.id)}
          alt={series.title}
          fill
          className="object-cover transition-transform duration-300 group-hover:scale-105"
          sizes="(max-width: 768px) 50vw, 200px"
          unoptimized
        />

        <div className="absolute inset-0 bg-gradient-to-t from-void via-void/20 to-transparent" />

        {series.reading_status ? (
          <span
            className={cn(
              "absolute left-2 top-2 rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide backdrop-blur-sm",
              statusBadgeStyle(series.reading_status),
            )}
          >
            {statusLabel(series.reading_status)}
          </span>
        ) : null}

        <div className="absolute inset-x-0 bottom-0 p-3">
          <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-white">
            {series.title}
          </h3>
          <p className="mt-0.5 text-xs text-white/70">
            {series.chapter_count} chapters
          </p>
        </div>

        <button
          type="button"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            toggleFavorite.mutate(series.id);
          }}
          className={cn(
            "absolute right-2 top-2 z-10 flex size-8 items-center justify-center rounded-full bg-black/50 backdrop-blur-sm transition-opacity",
            isHovered || series.is_favorite
              ? "opacity-100"
              : "opacity-100 sm:opacity-0 sm:group-hover:opacity-100",
            series.is_favorite ? "text-amber-400" : "text-white/70 hover:text-white",
          )}
          aria-label={series.is_favorite ? "Remove from favorites" : "Add to favorites"}
          title={series.is_favorite ? "Remove from favorites" : "Add to favorites"}
        >
          {series.is_favorite ? "★" : "☆"}
        </button>
      </div>

      <div className="mt-2 flex items-center justify-between px-0.5 text-xs">
        <div className="flex items-center gap-1 text-muted">
          {progress != null ? (
            <>
              <Star className="size-3 fill-amber-400 text-amber-400" aria-hidden />
              <span className="tabular-nums text-amber-400">
                {Math.round(progress.progress_pct)}%
              </span>
            </>
          ) : series.is_favorite ? (
            <>
              <Star className="size-3 fill-amber-400 text-amber-400" aria-hidden />
              <span className="text-amber-400">Favorite</span>
            </>
          ) : series.read_chapters > 0 ? (
            <span>
              {series.read_chapters}/{series.chapter_count} read
            </span>
          ) : (
            <span className="text-muted/60">—</span>
          )}
        </div>
        <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">
          {languageLabel(series.language)}
        </span>
      </div>
    </article>
  );
}

export function SeriesCard({ series }: SeriesCardProps) {
  const href = readerHref(series);
  const [isHovered, setIsHovered] = useState(false);
  const content = <SeriesCardContent series={series} isHovered={isHovered} />;

  if (!href) {
    return (
      <div onMouseEnter={() => setIsHovered(true)} onMouseLeave={() => setIsHovered(false)}>
        {content}
      </div>
    );
  }

  return (
    <Link
      href={href}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {content}
    </Link>
  );
}

export function SeriesListItem({ series }: SeriesCardProps) {
  const href = readerHref(series);
  const progress = series.reading_progress;
  const toggleFavorite = useToggleFavorite();

  const row = (
    <div className="glass-card flex items-center gap-4 rounded-2xl p-3 transition-colors hover:border-primary/30">
      <div className="relative size-16 shrink-0 overflow-hidden rounded-lg bg-surface-2">
        <Image
          src={coverUrl(series.id)}
          alt={series.title}
          fill
          className="object-cover"
          sizes="64px"
          unoptimized
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="truncate font-medium text-fg">{series.title}</h3>
          {series.reading_status ? (
            <span
              className={cn(
                "rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                statusBadgeStyle(series.reading_status),
              )}
            >
              {statusLabel(series.reading_status)}
            </span>
          ) : null}
        </div>
        {series.author ? (
          <p className="mt-0.5 truncate text-sm text-muted">{series.author}</p>
        ) : null}
        <p className="mt-1 text-xs text-muted">
          {series.chapter_count} chapters · {languageLabel(series.language)}
          {progress != null ? ` · ${Math.round(progress.progress_pct)}% read` : ""}
        </p>
      </div>
      <button
        type="button"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          toggleFavorite.mutate(series.id);
        }}
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-full bg-white/5 transition-colors hover:bg-white/10",
          series.is_favorite ? "text-amber-400" : "text-muted",
        )}
        aria-label={series.is_favorite ? "Remove from favorites" : "Add to favorites"}
      >
        {series.is_favorite ? "★" : "☆"}
      </button>
    </div>
  );

  if (!href) {
    return row;
  }

  return <Link href={href}>{row}</Link>;
}
