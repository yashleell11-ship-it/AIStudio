"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { Check, Star } from "lucide-react";
import { coverUrl } from "@/features/library/api";
import {
  DEFAULT_LIBRARY_DENSITY,
  type LibraryDensity,
  densityCoverSizes,
} from "@/features/library/density";
import { useToggleFavorite } from "@/features/library/hooks";
import type { SeriesSummary } from "@/features/library/types";
import { cn } from "@/lib/cn";
import { LibraryMembershipButton } from "./LibraryMembershipButton";

/** How a card reports a click on its checkbox (or on itself, in select mode). */
export type SeriesSelectHandler = (seriesId: number, shiftKey: boolean) => void;

export interface SeriesCardSelection {
  /**
   * Select mode: the card no longer navigates, and its checkbox is always
   * visible. Off, the checkbox only appears on hover and the card still links.
   */
  selecting: boolean;
  selected: boolean;
  onSelect: SeriesSelectHandler;
}

interface SeriesCardProps {
  series: SeriesSummary;
  density?: LibraryDensity;
  selection?: SeriesCardSelection;
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

const CHECKBOX_BASE =
  "flex size-6 items-center justify-center rounded-md border backdrop-blur-sm transition-all";

function checkboxTone(selected: boolean): string {
  return selected
    ? "border-primary bg-primary text-primary-fg"
    : "border-white/50 bg-black/50 text-transparent";
}

/**
 * The selection checkbox.
 *
 * Two shapes on purpose. Outside select mode the card is still a link, so this
 * is a real `<button role="checkbox">` that swallows the click which would
 * otherwise navigate and reads `shiftKey` off it to extend a range. Inside
 * select mode the whole card is the checkbox, so this becomes a plain indicator
 * — a button nested inside `role="checkbox"` is both invalid and a second
 * target that does the same thing.
 */
function SelectCheckbox({
  seriesId,
  title,
  selected,
  selecting,
  onSelect,
  className,
}: {
  seriesId: number;
  title: string;
  selected: boolean;
  selecting: boolean;
  onSelect: SeriesSelectHandler;
  className?: string;
}) {
  if (selecting) {
    return (
      <span
        aria-hidden
        className={cn(CHECKBOX_BASE, checkboxTone(selected), className)}
      >
        <Check className="size-4" />
      </span>
    );
  }

  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={selected}
      aria-label={`Select ${title}`}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onSelect(seriesId, event.shiftKey);
      }}
      className={cn(
        CHECKBOX_BASE,
        checkboxTone(selected),
        // Same reveal as the other cover controls: always there on touch, on
        // hover on a pointer device. `focus-visible` so tabbing to it does not
        // land on something invisible.
        selected
          ? "opacity-100"
          : "opacity-100 hover:border-white sm:opacity-0 sm:focus-visible:opacity-100 sm:group-hover:opacity-100",
        className,
      )}
    >
      <Check className="size-4" />
    </button>
  );
}

function SeriesCardContent({
  series,
  isHovered,
  density,
  selection,
}: {
  series: SeriesSummary;
  isHovered: boolean;
  density: LibraryDensity;
  selection?: SeriesCardSelection;
}) {
  const progress = series.reading_progress;
  const toggleFavorite = useToggleFavorite();
  const selected = selection?.selected ?? false;
  // Compact packs covers small enough that three overlaid controls would cover
  // the artwork, so only the checkbox survives there.
  const showRowActions = density !== "compact";

  return (
    <article
      className={cn(
        "group relative overflow-hidden rounded-2xl transition-all duration-300 hover:shadow-glow",
        selected && "ring-2 ring-primary ring-offset-2 ring-offset-bg",
      )}
    >
      <div className="relative aspect-[2/3] w-full overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-white/5 transition-all duration-300 group-hover:ring-primary/30">
        <Image
          src={coverUrl(series.id)}
          alt={series.title}
          fill
          className={cn(
            "object-cover transition-transform duration-300 group-hover:scale-105",
            selected && "scale-105 brightness-75",
          )}
          sizes={densityCoverSizes(density)}
          unoptimized
        />

        <div className="absolute inset-0 bg-gradient-to-t from-void via-void/20 to-transparent" />

        {/* Left corner stays the status badge's. The checkbox joins the existing
            control cluster on the right instead of fighting it for this spot. */}
        {series.reading_status && !selection?.selecting ? (
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
          <h3
            className={cn(
              "line-clamp-2 font-semibold leading-snug text-white",
              density === "compact" ? "text-xs" : "text-sm",
            )}
          >
            {series.title}
          </h3>
          {density === "compact" ? null : (
            <p className="mt-0.5 text-xs text-white/70">
              {series.chapter_count} chapters
            </p>
          )}
        </div>

        {selection || showRowActions ? (
          <div className="absolute right-2 top-2 z-10 flex items-center gap-1.5">
            {selection ? (
              <SelectCheckbox
                seriesId={series.id}
                title={series.title}
                selected={selected}
                selecting={selection.selecting}
                onSelect={selection.onSelect}
              />
            ) : null}
            {/* Hidden while selecting: a stray click on "remove from library"
                mid-selection is the one mistake with no undo on screen. */}
            {showRowActions && !selection?.selecting ? (
              <>
                {/* Every list that renders a card (library, local search hits,
                    recommendations, similar) INNER JOINs membership
                    server-side, so the series on screen is on the shelf by
                    construction. */}
                <LibraryMembershipButton
                  seriesId={series.id}
                  inLibrary
                  compact
                  className={cn(
                    "transition-opacity",
                    isHovered
                      ? "opacity-100"
                      : "opacity-100 sm:opacity-0 sm:group-hover:opacity-100",
                  )}
                />
                <button
                  type="button"
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    toggleFavorite.mutate(series.id);
                  }}
                  className={cn(
                    "flex size-8 items-center justify-center rounded-full bg-black/50 backdrop-blur-sm transition-opacity",
                    isHovered || series.is_favorite
                      ? "opacity-100"
                      : "opacity-100 sm:opacity-0 sm:group-hover:opacity-100",
                    series.is_favorite
                      ? "text-amber-400"
                      : "text-white/70 hover:text-white",
                  )}
                  aria-label={
                    series.is_favorite ? "Remove from favorites" : "Add to favorites"
                  }
                  title={
                    series.is_favorite ? "Remove from favorites" : "Add to favorites"
                  }
                >
                  {series.is_favorite ? "★" : "☆"}
                </button>
              </>
            ) : null}
          </div>
        ) : null}
      </div>

      {density === "compact" ? null : (
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
      )}
    </article>
  );
}

export function SeriesCard({
  series,
  density = DEFAULT_LIBRARY_DENSITY,
  selection,
}: SeriesCardProps) {
  const href = readerHref(series);
  const [isHovered, setIsHovered] = useState(false);
  const content = (
    <SeriesCardContent
      series={series}
      isHovered={isHovered}
      density={density}
      selection={selection}
    />
  );

  const hoverProps = {
    onMouseEnter: () => setIsHovered(true),
    onMouseLeave: () => setIsHovered(false),
  };

  // In select mode the whole card is the checkbox, so it must not also be a
  // link: a grid where every click both selects and navigates is unusable.
  if (selection?.selecting) {
    return (
      <div
        role="checkbox"
        aria-checked={selection.selected}
        aria-label={`Select ${series.title}`}
        tabIndex={0}
        onClick={(event) => selection.onSelect(series.id, event.shiftKey)}
        onKeyDown={(event) => {
          if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            selection.onSelect(series.id, event.shiftKey);
          }
        }}
        className="cursor-pointer select-none rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        {...hoverProps}
      >
        {content}
      </div>
    );
  }

  if (!href) {
    return <div {...hoverProps}>{content}</div>;
  }

  return (
    <Link href={href} {...hoverProps}>
      {content}
    </Link>
  );
}

export function SeriesListItem({ series, selection }: SeriesCardProps) {
  const href = readerHref(series);
  const progress = series.reading_progress;
  const toggleFavorite = useToggleFavorite();
  const selected = selection?.selected ?? false;

  const row = (
    <div
      className={cn(
        "glass-card group flex items-center gap-4 rounded-2xl p-3 transition-colors hover:border-primary/30",
        selected && "border-primary/60 bg-primary/5",
      )}
    >
      {selection ? (
        <SelectCheckbox
          seriesId={series.id}
          title={series.title}
          selected={selected}
          selecting={selection.selecting}
          onSelect={selection.onSelect}
          className="shrink-0"
        />
      ) : null}
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
      {selection?.selecting ? null : (
        <div className="flex shrink-0 items-center gap-1.5">
          <LibraryMembershipButton
            seriesId={series.id}
            inLibrary
            compact
            className="size-9 bg-white/5 hover:bg-white/10"
          />
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              toggleFavorite.mutate(series.id);
            }}
            className={cn(
              "flex size-9 items-center justify-center rounded-full bg-white/5 transition-colors hover:bg-white/10",
              series.is_favorite ? "text-amber-400" : "text-muted",
            )}
            aria-label={series.is_favorite ? "Remove from favorites" : "Add to favorites"}
          >
            {series.is_favorite ? "★" : "☆"}
          </button>
        </div>
      )}
    </div>
  );

  if (selection?.selecting) {
    return (
      <div
        role="checkbox"
        aria-checked={selected}
        aria-label={`Select ${series.title}`}
        tabIndex={0}
        onClick={(event) => selection.onSelect(series.id, event.shiftKey)}
        onKeyDown={(event) => {
          if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            selection.onSelect(series.id, event.shiftKey);
          }
        }}
        className="cursor-pointer select-none rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      >
        {row}
      </div>
    );
  }

  if (!href) {
    return row;
  }

  return <Link href={href}>{row}</Link>;
}
