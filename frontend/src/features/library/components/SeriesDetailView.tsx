"use client";

import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowLeft, BookOpen, Check, ChevronRight, Play, Star } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { libraryCoverUrl } from "@/features/library/api";
import {
  useAddTagToSeries,
  usePatchSeries,
  useSeries,
  useTags,
  useToggleFavorite,
} from "@/features/library/hooks";
import { readerChapterHref } from "@/features/reader/reader-link";
import { ApiError } from "@/types/api";
import type { SeriesId } from "@/types/api";
import {
  readScopedString,
  writeScopedString,
} from "@/lib/scoped-storage";
import { cn } from "@/lib/cn";
import { READING_STATUSES } from "../url-state";
import type { KnownChapter, SeriesDetail } from "../types";

/**
 * The poster: capped at `max-w-[220px]`, and 220px wide from `lg` up. Both a
 * `sizes` hint and the width the cover proxy renders to (`lib/cover-url.ts`).
 */
const POSTER_SIZES = "220px";

interface SeriesDetailViewProps {
  seriesId: number;
}

function statusBadgeStyle(status: string): string {
  switch (status) {
    case "reading":
      return "bg-primary/15 text-primary border-primary/30";
    case "completed":
      return "bg-success/15 text-success border-success/30";
    case "on_hold":
      return "bg-accent/15 text-accent border-accent/30";
    default:
      return "bg-white/5 text-muted border-border/50";
  }
}

type ChapterSort = "newest" | "oldest";

function chapterOrder(a: KnownChapter, b: KnownChapter): number {
  const an = a.number ?? Number.NEGATIVE_INFINITY;
  const bn = b.number ?? Number.NEGATIVE_INFINITY;
  return an - bn;
}

export function SeriesDetailView({ seriesId }: SeriesDetailViewProps) {
  const seriesQuery = useSeries(seriesId);
  const series = seriesQuery.data;

  const tagsQuery = useTags();
  const toggleFavorite = useToggleFavorite();
  const patchSeries = usePatchSeries();
  const addTag = useAddTagToSeries();
  const [showTagPicker, setShowTagPicker] = useState(false);

  const sortKey = series ? `mm.chapter-sort:${series.source_id}:${series.series_key}` : null;
  const [sort, setSort] = useState<ChapterSort>(() => {
    if (!sortKey) return "newest";
    return readScopedString(sortKey) === "oldest" ? "oldest" : "newest";
  });
  const setSortPersisted = (next: ChapterSort) => {
    setSort(next);
    if (sortKey) writeScopedString(sortKey, next);
  };

  const orderedChapters = useMemo(() => {
    if (!series) return [];
    const asc = [...series.chapters].sort(chapterOrder);
    return sort === "newest" ? asc.reverse() : asc;
  }, [series, sort]);

  const resumeTarget = useMemo(() => {
    if (!series) return null;
    const asc = [...series.chapters].sort(chapterOrder);
    // First chapter with progress that is not completed, else the first unread,
    // else the very first chapter.
    const inProgress = asc.find((chapter) => {
      const p = series.progress[chapter.key];
      return p != null && !p.is_completed;
    });
    if (inProgress) {
      return {
        chapter: inProgress,
        page: series.progress[inProgress.key]?.last_page ?? 1,
      };
    }
    const firstUnread = asc.find((chapter) => !series.progress[chapter.key]);
    const target = firstUnread ?? asc[0] ?? null;
    return target ? { chapter: target, page: 1 } : null;
  }, [series]);

  if (seriesQuery.isLoading) {
    return (
      <div className="min-h-full bg-bg" aria-busy="true" aria-label="Loading series">
        <div className="h-[280px] animate-pulse bg-surface-2" />
        <div className="mx-auto max-w-6xl px-6 py-8 md:px-10">
          <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
            <div className="aspect-[2/3] animate-pulse rounded-2xl bg-surface-2" />
            <div className="space-y-4">
              <div className="h-10 w-2/3 animate-pulse rounded bg-surface-2" />
              <div className="h-4 w-full animate-pulse rounded bg-surface-2" />
              <div className="h-24 animate-pulse rounded-xl bg-surface-2" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (seriesQuery.error || !series) {
    const message =
      seriesQuery.error instanceof ApiError
        ? seriesQuery.error.message
        : "Failed to load series.";
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="text-danger">{message}</p>
        <Link
          href="/library"
          className="mt-4 inline-flex h-10 items-center justify-center rounded-full bg-primary px-5 text-sm font-medium text-primary-fg transition-colors hover:bg-primary-hover"
        >
          Back to library
        </Link>
      </div>
    );
  }

  const detail: SeriesDetail = series;
  const seriesRef: SeriesId = {
    sourceId: detail.source_id,
    seriesKey: detail.series_key,
  };
  // One URL for both the poster and the blurred backdrop behind it, which is
  // one fetch rather than two: the backdrop is `blur-sm` at 35% brightness
  // under a gradient, so it has no detail to lose from being painted at the
  // poster's width, and a second `100vw` request for it would be the largest
  // cover download on the page.
  const cover = libraryCoverUrl(detail.cover_url, POSTER_SIZES);
  const hasProgress = Object.keys(detail.progress).length > 0;

  return (
    <div className="min-h-full bg-bg">
      <section className="relative h-[280px] overflow-hidden md:h-[320px]">
        <Image
          src={cover}
          alt=""
          fill
          className="object-cover brightness-[0.35] blur-sm"
          sizes="100vw"
          unoptimized
          aria-hidden
        />
        <div className="absolute inset-0 bg-gradient-to-b from-void/60 via-void/80 to-bg" />
        <div className="absolute inset-x-0 top-0 px-6 py-4 md:px-10">
          <Link
            href="/library"
            className="inline-flex items-center gap-1.5 text-sm text-white/70 transition-colors hover:text-white"
          >
            <ArrowLeft className="size-4" />
            Back to library
          </Link>
        </div>
      </section>

      <div className="relative mx-auto max-w-6xl px-6 pb-10 md:px-10">
        <div className="-mt-36 grid gap-8 lg:grid-cols-[220px_1fr] lg:gap-10">
          <div className="mx-auto w-full max-w-[220px] lg:mx-0 lg:sticky lg:top-24 lg:self-start">
            <div className="relative aspect-[2/3] overflow-hidden rounded-3xl shadow-glow ring-1 ring-white/10">
              <Image
                src={cover}
                alt={detail.title}
                fill
                className="object-cover"
                sizes={POSTER_SIZES}
                unoptimized
                priority
              />
            </div>
          </div>

          <div className="pt-2 lg:pt-16">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <h1 className="text-3xl font-bold tracking-tight text-fg md:text-4xl">
                  {detail.title}
                </h1>
              </div>
              <div className="flex shrink-0 flex-wrap items-start gap-2">
                <Button
                  variant={detail.is_favorite ? "primary" : "secondary"}
                  onClick={() =>
                    toggleFavorite.mutate({
                      followedId: detail.id,
                      isFavorite: !detail.is_favorite,
                    })
                  }
                  aria-label={
                    detail.is_favorite ? "Remove from favorites" : "Add to favorites"
                  }
                  className={cn(
                    "rounded-full",
                    detail.is_favorite
                      ? "bg-primary/20 text-primary hover:bg-primary/30"
                      : "border border-border/50 bg-white/5 hover:bg-white/10",
                  )}
                >
                  <Star className={cn("size-4", detail.is_favorite && "fill-primary")} />
                  {detail.is_favorite ? "Favorited" : "Add Favorite"}
                </Button>
              </div>
            </div>

            {detail.author ? (
              <p className="mt-3 text-base text-muted">by {detail.author}</p>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <label className="sr-only" htmlFor="reading-status">
                Reading status
              </label>
              <select
                id="reading-status"
                value={detail.reading_status}
                onChange={(event) =>
                  patchSeries.mutate({
                    followedId: detail.id,
                    body: { reading_status: event.target.value },
                  })
                }
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-wide",
                  statusBadgeStyle(detail.reading_status),
                )}
              >
                {READING_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() =>
                  patchSeries.mutate({
                    followedId: detail.id,
                    body: { notify: !detail.notify },
                  })
                }
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-medium",
                  detail.notify
                    ? "border-primary/30 bg-primary/10 text-primary"
                    : "border-border/50 bg-white/5 text-muted",
                )}
              >
                {detail.notify ? "Notifications on" : "Notifications off"}
              </button>
            </div>

            <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted">
              <span>{detail.chapters.length} chapters</span>
              {detail.genres && detail.genres.length > 0 ? (
                <span>{detail.genres.slice(0, 4).join(", ")}</span>
              ) : null}
            </div>

            {resumeTarget ? (
              <PrimaryPillButton
                href={readerChapterHref(
                  { ...seriesRef, chapterKey: resumeTarget.chapter.key },
                  resumeTarget.page,
                )}
                className="mt-6 shadow-glow"
                icon={<Play className="size-4 fill-current" />}
              >
                {hasProgress ? "Continue" : "Read"}
              </PrimaryPillButton>
            ) : null}

            <div className="mt-6 flex flex-wrap items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowTagPicker(!showTagPicker)}
                className="text-muted hover:text-fg"
              >
                + Tag
              </Button>
            </div>
            {showTagPicker && tagsQuery.data ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {tagsQuery.data.map((tag) => (
                  <Badge
                    key={tag.id}
                    variant="default"
                    className="cursor-pointer border-border/50 bg-white/5 hover:bg-primary/15"
                    onClick={() => {
                      addTag.mutate({ ref: seriesRef, tagId: tag.id });
                      setShowTagPicker(false);
                    }}
                  >
                    + {tag.name}
                  </Badge>
                ))}
              </div>
            ) : null}

            {detail.description ? (
              <p className="mt-6 max-w-3xl text-sm leading-relaxed text-fg/80">
                {detail.description}
              </p>
            ) : null}
          </div>
        </div>

        <section className="mt-10">
          <div className="mb-4 flex items-center gap-2">
            <BookOpen className="size-4 text-primary" aria-hidden />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-fg">
              Chapters
            </h2>
            <span className="text-xs text-muted">({detail.chapters.length})</span>
            <div className="ml-auto flex gap-1 text-xs">
              {(["newest", "oldest"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setSortPersisted(option)}
                  className={cn(
                    "rounded-full px-3 py-1 capitalize transition-colors",
                    sort === option
                      ? "bg-primary/15 text-primary"
                      : "text-muted hover:text-fg",
                  )}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>

          <div className="glass-panel divide-y divide-border/60 overflow-hidden rounded-3xl border border-border">
            {orderedChapters.length === 0 ? (
              <p className="p-6 text-sm text-muted">No chapters found for this series.</p>
            ) : (
              orderedChapters.map((chapter, index) => {
                const progress = detail.progress[chapter.key];
                const isCompleted = progress?.is_completed ?? false;
                const inProgress = progress != null && !isCompleted;
                return (
                  <Link
                    key={chapter.key}
                    href={readerChapterHref(
                      { ...seriesRef, chapterKey: chapter.key },
                      progress?.last_page,
                    )}
                    className={cn(
                      "group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-primary/[0.06]",
                      isCompleted && "bg-black/25",
                    )}
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/5 font-mono text-xs tabular-nums text-muted transition-colors group-hover:bg-primary/20 group-hover:text-primary">
                      {chapter.number ?? index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p
                        className={cn(
                          "truncate font-medium transition-colors group-hover:text-primary",
                          isCompleted ? "text-muted" : "text-fg",
                        )}
                      >
                        {chapter.title ??
                          (chapter.number != null
                            ? `Chapter ${chapter.number}`
                            : chapter.key)}
                      </p>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                        {inProgress && chapter.page_count ? (
                          <span>
                            {progress!.last_page}/{chapter.page_count} pages
                          </span>
                        ) : chapter.page_count ? (
                          <span>{chapter.page_count} pages</span>
                        ) : null}
                        {isCompleted ? (
                          <span className="inline-flex items-center gap-1 rounded-full border border-border/50 bg-white/5 px-1.5 py-0.5">
                            <Check className="size-3" aria-hidden />
                            Read
                          </span>
                        ) : null}
                      </div>
                    </div>
                    {inProgress ? (
                      <Badge
                        variant="primary"
                        className="shrink-0 bg-primary/20 text-primary"
                      >
                        In progress
                      </Badge>
                    ) : (
                      <ChevronRight className="size-4 shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                    )}
                  </Link>
                );
              })
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
