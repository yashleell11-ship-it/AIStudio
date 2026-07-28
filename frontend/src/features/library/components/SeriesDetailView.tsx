"use client";

import Image from "next/image";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  Check,
  ChevronRight,
  Cloud,
  Download,
  DownloadCloud,
  Play,
  Sparkles,
  Star,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { coverUrl } from "@/features/library/api";
import {
  useAddTagToSeries,
  useMetadataQuality,
  useRemoveTagFromSeries,
  useSeries,
  useSimilarSeries,
  useTags,
  useToggleFavorite,
} from "@/features/library/hooks";
import { prefetchReaderChapter } from "@/features/reader/hooks";
import { useQueueChapters } from "@/features/downloads/hooks";
import { sourceReaderChapterPath } from "@/features/sources/hooks";
import { ApiError } from "@/types/api";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { cn } from "@/lib/cn";
import { LibraryMembershipButton } from "./LibraryMembershipButton";
import { SeriesCard } from "./SeriesCard";

interface SeriesDetailViewProps {
  seriesId: number;
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

function statusBadgeStyle(status: string): string {
  switch (status) {
    case "reading":
      return "bg-primary/15 text-primary border-primary/30";
    case "completed":
      return "bg-success/15 text-success border-success/30";
    case "on_hold":
    case "on-hold":
      return "bg-accent/15 text-accent border-accent/30";
    default:
      return "bg-white/5 text-muted border-border/50";
  }
}

export function SeriesDetailView({ seriesId }: SeriesDetailViewProps) {
  const seriesQuery = useSeries(seriesId);
  const queryClient = useQueryClient();
  const series = seriesQuery.data;

  const similarQuery = useSimilarSeries(seriesId, 8);
  const metadataQuery = useMetadataQuality(seriesId);
  const tagsQuery = useTags();
  const toggleFavorite = useToggleFavorite();
  const addTag = useAddTagToSeries();
  const removeTag = useRemoveTagFromSeries();
  const queueChapters = useQueueChapters();
  const [showTagPicker, setShowTagPicker] = useState(false);

  useEffect(() => {
    if (!series) return;
    const progress = series.reading_progress;
    if (progress?.chapter_id) {
      prefetchReaderChapter(queryClient, progress.chapter_id);
    } else if (series.first_chapter_id != null) {
      prefetchReaderChapter(queryClient, series.first_chapter_id);
    }
    for (const chapter of series.chapters.slice(0, 5)) {
      if (chapter.id != null) {
        prefetchReaderChapter(queryClient, chapter.id);
      }
    }
  }, [queryClient, series]);

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

  const progress = series.reading_progress;
  const continueHref =
    progress != null
      ? `/reader/${series.id}/${progress.chapter_id}?page=${progress.last_page}`
      : series.first_chapter_id != null
        ? `/reader/${series.id}/${series.first_chapter_id}`
        : null;

  const prefetchChapter = (chapterId: number) => {
    prefetchReaderChapter(queryClient, chapterId);
  };

  const sourceId = series.source_id ?? null;
  const sourceSeriesId = series.source_series_id ?? null;

  const downloadChapter = (sourceChapterId: string) => {
    if (!sourceId || !sourceSeriesId) return;
    queueChapters.mutate({
      source_id: sourceId,
      series_id: sourceSeriesId,
      chapter_ids: [sourceChapterId],
      series_title: series.title,
    });
  };

  const metadata = metadataQuery.data;
  const similar = similarQuery.data ?? [];

  return (
    <div className="min-h-full bg-bg">
      {/* Hero banner */}
      <section className="relative h-[280px] overflow-hidden md:h-[320px]">
        <Image
          src={coverUrl(series.id)}
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
          {/* Cover */}
          <div className="mx-auto w-full max-w-[220px] lg:mx-0 lg:sticky lg:top-24 lg:self-start">
            <div className="relative aspect-[2/3] overflow-hidden rounded-3xl shadow-glow ring-1 ring-white/10">
              <Image
                src={coverUrl(series.id)}
                alt={series.title}
                fill
                className="object-cover"
                sizes="220px"
                unoptimized
                priority
              />
            </div>
          </div>

          {/* Info */}
          <div className="pt-2 lg:pt-16">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <h1 className="text-3xl font-bold tracking-tight text-fg md:text-4xl">
                  {series.title}
                </h1>
                {series.original_title ? (
                  <p className="mt-1 text-sm italic text-muted">{series.original_title}</p>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-wrap items-start gap-2">
                {/* This route is NOT membership-gated — `GET /library/series/{id}`
                    answers for any catalog series — so the shelf state comes from
                    the payload's own `in_library` rather than being assumed. */}
                <LibraryMembershipButton
                  seriesId={series.id}
                  inLibrary={series.in_library}
                />
                <Button
                  variant={series.is_favorite ? "primary" : "secondary"}
                  onClick={() => toggleFavorite.mutate(series.id)}
                  aria-label={series.is_favorite ? "Remove from favorites" : "Add to favorites"}
                  className={cn(
                    "rounded-full",
                    series.is_favorite
                      ? "bg-primary/20 text-primary hover:bg-primary/30"
                      : "border border-border/50 bg-white/5 hover:bg-white/10",
                  )}
                >
                  <Star
                    className={cn("size-4", series.is_favorite && "fill-primary")}
                  />
                  {series.is_favorite ? "Favorited" : "Add Favorite"}
                </Button>
              </div>
            </div>

            {series.author ? (
              <p className="mt-3 text-base text-muted">by {series.author}</p>
            ) : null}
            {series.artist ? (
              <p className="text-sm text-muted/80">Art by {series.artist}</p>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center gap-2">
              {series.reading_status ? (
                <span
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-wide",
                    statusBadgeStyle(series.reading_status),
                  )}
                >
                  {series.reading_status.replace(/_/g, " ")}
                </span>
              ) : null}
              <span className="rounded-full border border-border/50 bg-white/5 px-3 py-1 text-xs text-muted">
                {languageLabel(series.language)}
              </span>
              {series.year ? (
                <span className="rounded-full border border-border/50 bg-white/5 px-3 py-1 text-xs text-muted">
                  {series.year}
                </span>
              ) : null}
            </div>

            <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted">
              <span>{series.chapter_count} chapters</span>
              <span>{series.page_count.toLocaleString()} pages</span>
              {progress != null ? (
                <span className="font-medium text-primary">
                  {Math.round(progress.progress_pct)}% read
                </span>
              ) : null}
            </div>

            {continueHref ? (
              <PrimaryPillButton
                href={continueHref}
                className="mt-6 shadow-glow"
                icon={<Play className="size-4 fill-current" />}
              >
                {progress ? "Continue Reading" : "Start Reading"}
              </PrimaryPillButton>
            ) : null}

            {/* Tags */}
            <div className="mt-6 flex flex-wrap items-center gap-2">
              {series.tags.map((tag) => (
                <Badge
                  key={tag.id}
                  variant="default"
                  className="cursor-pointer border-border/50 bg-white/5 hover:bg-red-500/10"
                  onClick={() => removeTag.mutate({ seriesId: series.id, tagId: tag.id })}
                  title="Click to remove"
                >
                  {tag.name} ×
                </Badge>
              ))}
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
                {tagsQuery.data
                  .filter((t) => !series.tags.some((st) => st.id === t.id))
                  .map((tag) => (
                    <Badge
                      key={tag.id}
                      variant="default"
                      className="cursor-pointer border-border/50 bg-white/5 hover:bg-primary/15"
                      onClick={() => {
                        addTag.mutate({ seriesId: series.id, tagId: tag.id });
                        setShowTagPicker(false);
                      }}
                    >
                      + {tag.name}
                    </Badge>
                  ))}
              </div>
            ) : null}

            {series.collections.length > 0 ? (
              <div className="mt-3 text-sm text-muted">
                In collections:{" "}
                {series.collections.map((c, i) => (
                  <span key={c.id}>
                    <Link
                      href={`/library/collections/${c.id}`}
                      className="text-primary hover:underline"
                    >
                      {c.name}
                    </Link>
                    {i < series.collections.length - 1 && ", "}
                  </span>
                ))}
              </div>
            ) : null}

            {series.description ? (
              <p className="mt-6 max-w-3xl text-sm leading-relaxed text-fg/80">
                {series.description}
              </p>
            ) : null}
          </div>
        </div>

        {/* Metadata Quality */}
        {metadata ? (
          <section className="glass-panel mt-10 rounded-3xl border border-border p-6">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-primary" aria-hidden />
                <h2 className="text-sm font-semibold uppercase tracking-wider text-fg">
                  Metadata Quality
                </h2>
              </div>
              <span className="font-mono text-sm tabular-nums text-muted">
                {metadata.score}/100
              </span>
            </div>
            <Progress
              value={metadata.score}
              className="mb-4 h-2 bg-white/10 [&>div]:bg-gradient-to-r [&>div]:from-accent [&>div]:to-primary"
            />
            {metadata.suggestions.length > 0 ? (
              <div className="space-y-1.5">
                {metadata.suggestions.map((s) => (
                  <p key={s} className="text-sm text-muted">
                    • {s}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-sm text-success">All metadata fields complete!</p>
            )}
          </section>
        ) : null}

        {/* Chapters */}
        <section className="mt-10">
          <div className="mb-4 flex items-center gap-2">
            <BookOpen className="size-4 text-primary" aria-hidden />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-fg">
              Chapters
            </h2>
            <span className="text-xs text-muted">({series.chapters.length})</span>
          </div>

          <div className="glass-panel divide-y divide-border/60 overflow-hidden rounded-3xl border border-border">
            {series.chapters.length === 0 ? (
              <p className="p-6 text-sm text-muted">No chapters found for this series.</p>
            ) : (
              series.chapters.map((chapter, index) => {
                const isDownloaded = chapter.is_downloaded ?? chapter.id != null;
                const isCurrent =
                  chapter.id != null && progress?.chapter_id === chapter.id;
                const rowKey =
                  chapter.id != null
                    ? `local-${chapter.id}`
                    : `remote-${chapter.source_chapter_id ?? index}`;

                const numberBadge = (
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/5 font-mono text-xs tabular-nums text-muted transition-colors group-hover:bg-primary/20 group-hover:text-primary">
                    {chapter.number ?? index + 1}
                  </span>
                );

                const chapterBody = (
                  <div className="min-w-0 flex-1">
                    <p
                      className={cn(
                        "truncate font-medium transition-colors group-hover:text-primary",
                        chapter.is_read ? "text-muted" : "text-fg",
                      )}
                    >
                      {chapter.title}
                    </p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                      {chapter.page_count > 0 ? (
                        <span>{chapter.page_count} pages</span>
                      ) : null}
                      {isDownloaded ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-success/30 bg-success/10 px-1.5 py-0.5 text-success">
                          <DownloadCloud className="size-3" aria-hidden />
                          Downloaded
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-primary">
                          <Cloud className="size-3" aria-hidden />
                          Online
                        </span>
                      )}
                      {chapter.is_read ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-border/50 bg-white/5 px-1.5 py-0.5">
                          <Check className="size-3" aria-hidden />
                          Read
                        </span>
                      ) : null}
                    </div>
                  </div>
                );

                if (isDownloaded && chapter.id != null) {
                  const localId = chapter.id;
                  return (
                    <Link
                      key={rowKey}
                      href={`/reader/${series.id}/${localId}`}
                      onMouseEnter={() => prefetchChapter(localId)}
                      onFocus={() => prefetchChapter(localId)}
                      className={cn(
                        "group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-primary/[0.06]",
                        chapter.is_read && "bg-black/25",
                      )}
                    >
                      {numberBadge}
                      {chapterBody}
                      {isCurrent ? (
                        <Badge variant="primary" className="shrink-0 bg-primary/20 text-primary">
                          In progress
                        </Badge>
                      ) : (
                        <ChevronRight className="size-4 shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                      )}
                    </Link>
                  );
                }

                // Remote-only chapter: offer Read Online + Download.
                const canReadOnline =
                  sourceId != null &&
                  sourceSeriesId != null &&
                  chapter.source_chapter_id != null;
                return (
                  <div
                    key={rowKey}
                    className={cn(
                      "group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-primary/[0.06]",
                      chapter.is_read && "bg-black/25",
                    )}
                  >
                    {numberBadge}
                    {chapterBody}
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      {canReadOnline ? (
                        <Link
                          href={sourceReaderChapterPath(
                            sourceId!,
                            sourceSeriesId!,
                            chapter.source_chapter_id!,
                          )}
                        >
                          <Button variant="ghost" size="sm">
                            Read Online
                          </Button>
                        </Link>
                      ) : null}
                      {canReadOnline ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={queueChapters.isPending}
                          onClick={() => downloadChapter(chapter.source_chapter_id!)}
                        >
                          <Download className="size-3.5" aria-hidden />
                          Download
                        </Button>
                      ) : null}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* Similar Series */}
        {similar.length > 0 ? (
          <section className="mt-10">
            <div className="mb-4 flex items-center gap-2">
              <Sparkles className="size-4 text-primary" aria-hidden />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-fg">
                Similar Series
              </h2>
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
              {similar.map((s) => (
                <SeriesCard key={s.id} series={s} />
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
