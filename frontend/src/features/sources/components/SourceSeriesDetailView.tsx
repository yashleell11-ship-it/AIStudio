"use client";

import Image from "next/image";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookX, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { OfflineState } from "@/components/ui/offline-state";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import {
  followKey,
  useFollow,
  useFollowedIndex,
  useUnfollow,
} from "@/features/library/hooks";
import { useSeriesProgress } from "@/features/reader/hooks";
import { ApiError } from "@/types/api";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";
import { cn } from "@/lib/cn";
import { createHoverIntent } from "@/lib/hover-intent";
import { sourceImageUrl } from "../api";
import { chapterLabel } from "../chapter-label";
import { resolveChapterListState } from "../chapter-list-state";
import {
  prefetchSourceReaderChapter,
  sourceReaderChapterPath,
  useSourceChapters,
  useSourceSeriesDetail,
} from "../hooks";
import { resolveSeriesProgress } from "../series-progress";
import { useSourceSeriesProgress } from "../source-progress";
import {
  ChapterRowsSkeleton,
  SourceSeriesDetailSkeleton,
} from "./SourceSeriesDetailSkeleton";

type ChapterSortOrder = "newest" | "oldest";

interface SourceSeriesDetailViewProps {
  sourceId: string;
  seriesId: string;
}

export function SourceSeriesDetailView({
  sourceId,
  seriesId,
}: SourceSeriesDetailViewProps) {
  const seriesQuery = useSourceSeriesDetail(sourceId, seriesId);
  const chaptersQuery = useSourceChapters(sourceId, seriesId);
  const followedIndex = useFollowedIndex();
  const followedId =
    followedIndex.index.get(followKey({ sourceId, seriesKey: seriesId })) ??
    null;
  const followMutation = useFollow();
  const unfollowMutation = useUnfollow();
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<ChapterSortOrder>("newest");
  // Reading position is server-owned (`POST /reader/progress`); the local store
  // only still carries positions adopted from a pre-scoping device. Reading the
  // local store alone is what left every chapter looking unread — see
  // `series-progress.ts`.
  const localProgress = useSourceSeriesProgress(sourceId, seriesId);
  const seriesProgressQuery = useSeriesProgress({
    sourceId,
    seriesKey: seriesId,
  });
  const { map: progressMap, latest: latestRead } = useMemo(
    () =>
      resolveSeriesProgress({
        serverRows: seriesProgressQuery.data ?? [],
        localMap: localProgress.map,
      }),
    [seriesProgressQuery.data, localProgress.map],
  );

  const series = seriesQuery.data;
  const chapters = useMemo(() => chaptersQuery.data ?? [], [chaptersQuery.data]);

  const sortedChapters = useMemo(() => {
    const copy = [...chapters];
    copy.sort((a, b) => {
      if (a.number == null && b.number == null) return 0;
      if (a.number == null) return 1; // nulls always last
      if (b.number == null) return -1;
      return sortOrder === "newest" ? b.number - a.number : a.number - b.number;
    });
    return copy;
  }, [chapters, sortOrder]);

  // Earliest numbered chapter — the "start from the beginning" target when the
  // reader has no saved progress. Falls back to raw order if none are numbered.
  const earliestChapter = useMemo(() => {
    let earliest: (typeof chapters)[number] | null = null;
    for (const chapter of chapters) {
      if (chapter.number == null) continue;
      if (!earliest || (earliest.number != null && chapter.number < earliest.number)) {
        earliest = chapter;
      }
    }
    return earliest ?? chapters[0] ?? null;
  }, [chapters]);

  useEffect(() => {
    for (const chapter of chapters.slice(0, 5)) {
      prefetchSourceReaderChapter(queryClient, sourceId, seriesId, chapter.id);
    }
  }, [chapters, queryClient, seriesId, sourceId]);

  /**
   * Hover/focus prefetch, gated on the pointer actually settling. A `mouseenter`
   * per row meant one chapter fetch per row crossed — sweeping down a long
   * chapter list fired dozens in a second. See `lib/hover-intent.ts`.
   */
  // Through a ref so the intent, created once, always prefetches for the
  // series currently on screen even if the route swaps props without a remount.
  const prefetchRef = useRef<(chapterId: string) => void>(() => {});
  prefetchRef.current = (chapterId: string) => {
    prefetchSourceReaderChapter(queryClient, sourceId, seriesId, chapterId);
  };
  const hoverIntent = useRef(
    createHoverIntent<string>((chapterId) => prefetchRef.current(chapterId)),
  );
  useEffect(() => {
    const intent = hoverIntent.current;
    return () => intent.dispose();
  }, []);
  const prefetchOnIntent = useCallback((chapterId: string) => {
    hoverIntent.current.enter(chapterId);
  }, []);
  const cancelPrefetchIntent = useCallback(() => {
    hoverIntent.current.leave();
  }, []);

  // An empty answer means something different depending on what the series
  // summary claims the source holds — see `resolveChapterListState`.
  const chapterListState = resolveChapterListState({
    isLoading: chaptersQuery.isLoading,
    error: chaptersQuery.error,
    chapterCount: chapters.length,
    reportedChapterCount: series?.chapter_count ?? 0,
  });

  const seriesViewState = resolveViewState({
    isLoading: seriesQuery.isLoading,
    error: seriesQuery.error,
    // A resolved request with no payload is a failure to load, not an empty
    // series — every branch below needs `series` to render anything at all.
    isEmpty: !series,
  });

  if (seriesViewState === "loading") {
    return <SourceSeriesDetailSkeleton />;
  }

  if (seriesViewState === "offline") {
    return (
      <div className="p-6">
        <OfflineState
          reason="This series page needs a connection to load."
          onRetry={() => void seriesQuery.refetch()}
        />
      </div>
    );
  }

  if (seriesViewState !== "content" || !series) {
    return (
      <div className="p-6">
        <EmptyState
          tone="error"
          icon={TriangleAlert}
          title="Couldn't load this series"
          description={apiErrorMessage(seriesQuery.error, "The source did not answer.")}
          action={{ label: "Try again", onClick: () => void seriesQuery.refetch() }}
          secondaryAction={{ label: "Back to source", href: `/sources/${sourceId}` }}
        />
      </div>
    );
  }

  // "Continue" resumes the most recently read chapter at its saved page;
  // otherwise "Read Online" starts from the earliest chapter at page 1.
  const primaryChapterId = latestRead ? latestRead.chapterId : earliestChapter?.id ?? null;
  const primaryHref = latestRead
    ? `${sourceReaderChapterPath(sourceId, seriesId, latestRead.chapterId)}?page=${latestRead.progress.page}`
    : earliestChapter
      ? sourceReaderChapterPath(sourceId, seriesId, earliestChapter.id)
      : null;
  const primaryLabel = latestRead ? "Continue" : "Read Online";

  const prefetchChapter = (chapterId: string) => {
    prefetchSourceReaderChapter(queryClient, sourceId, seriesId, chapterId);
  };

  const toggleFollow = async () => {
    setFeedback(null);
    try {
      if (followedId !== null) {
        await unfollowMutation.mutateAsync(followedId);
        setFeedback(`Unfollowed ${series.title}.`);
      } else {
        await followMutation.mutateAsync({ sourceId, seriesKey: seriesId });
        setFeedback(`Following ${series.title}. New chapters will notify you.`);
      }
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Failed to update follow status.");
    }
  };

  const followBusy = followMutation.isPending || unfollowMutation.isPending;
  const isFollowed = followedId !== null;

  return (
    <div className="p-6">
      <div className="mb-6">
        <Link href={`/sources/${sourceId}`} className="text-sm text-muted hover:text-fg">
          ← Back to source
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <Card className="overflow-hidden rounded-3xl lg:sticky lg:top-24 lg:self-start">
          <div className="relative aspect-[2/3] w-full bg-surface-2">
            <Image
              src={sourceImageUrl(series.cover_url)}
              alt={series.title}
              fill
              className="object-cover"
              sizes="220px"
              unoptimized
            />
          </div>
        </Card>

        <div>
          <h1 className="font-display text-4xl leading-tight text-fg">{series.title}</h1>
          {series.author && <p className="mt-2 text-muted">Author: {series.author}</p>}
          {series.artist && <p className="mt-1 text-muted">Artist: {series.artist}</p>}
          {series.status && (
            <Badge variant="primary" className="mt-3 capitalize">
              {series.status}
            </Badge>
          )}
          {series.genres.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {series.genres.map((genre) => (
                <Link
                  key={genre}
                  href={`/sources/${encodeURIComponent(sourceId)}?genre=${encodeURIComponent(genre)}`}
                >
                  <Badge
                    variant="default"
                    className="cursor-pointer transition-colors hover:border-primary/50 hover:bg-primary/10"
                  >
                    {genre}
                  </Badge>
                </Link>
              ))}
            </div>
          )}
          {series.description && (
            <p className="mt-4 max-w-3xl text-sm leading-6 text-muted">{series.description}</p>
          )}

          <div className="mt-6 flex flex-wrap gap-2">
            {primaryHref && (
              <span
                className="inline-flex"
                onMouseEnter={() => primaryChapterId && prefetchChapter(primaryChapterId)}
                onFocus={() => primaryChapterId && prefetchChapter(primaryChapterId)}
              >
                <PrimaryPillButton href={primaryHref}>{primaryLabel}</PrimaryPillButton>
              </span>
            )}
            <Button
              variant={isFollowed ? "ghost" : "secondary"}
              disabled={followBusy}
              onClick={toggleFollow}
            >
              {followBusy
                ? isFollowed
                  ? "Unfollowing…"
                  : "Following…"
                : isFollowed
                  ? "Unfollow"
                  : "Follow"}
            </Button>
          </div>
          {feedback && <p className="mt-3 text-sm text-muted">{feedback}</p>}
        </div>
      </div>

      <Card className="mt-8">
        <CardHeader className="flex-row items-center justify-between gap-3">
          <CardTitle>Chapters</CardTitle>
          {chapters.length > 1 && (
            <div className="inline-flex overflow-hidden rounded-lg border border-border/50">
              {(["newest", "oldest"] as const).map((order) => (
                <button
                  key={order}
                  type="button"
                  onClick={() => setSortOrder(order)}
                  className={cn(
                    "px-3 py-1 text-xs font-medium capitalize transition-colors",
                    sortOrder === order
                      ? "bg-primary text-primary-fg"
                      : "text-muted hover:bg-white/5 hover:text-fg",
                  )}
                >
                  {order}
                </button>
              ))}
            </div>
          )}
        </CardHeader>
        <CardContent className="divide-y divide-border">
          {chapterListState === "loading" ? (
            <ChapterRowsSkeleton />
          ) : chapterListState === "offline" ? (
            <OfflineState
              reason="The chapter list needs a connection to load."
              onRetry={() => void chaptersQuery.refetch()}
            />
          ) : chapterListState === "error" ? (
            <EmptyState
              tone="error"
              icon={TriangleAlert}
              title="Couldn't load the chapter list"
              description={apiErrorMessage(
                chaptersQuery.error,
                "The source did not answer.",
              )}
              action={{ label: "Try again", onClick: () => void chaptersQuery.refetch() }}
            />
          ) : chapterListState === "unavailable" ? (
            <EmptyState
              tone="error"
              icon={TriangleAlert}
              title="Chapters didn't come through"
              description={`This source lists ${series.chapter_count.toLocaleString()} chapters for this series but returned none just now — usually the source, not you.`}
              action={{ label: "Try again", onClick: () => void chaptersQuery.refetch() }}
            />
          ) : chapterListState === "empty" ? (
            <EmptyState
              icon={BookX}
              title="No chapters yet"
              description="This source has not published any chapters for this series."
              action={{ label: "Back to source", href: `/sources/${sourceId}` }}
            />
          ) : (
            sortedChapters.map((chapter) => {
              const label = chapterLabel(chapter);
              const progress = progressMap[chapter.id] ?? null;
              const completed = progress?.completed ?? false;
              const reading = progress != null && !completed;
              const pageCount = progress?.pageCount || chapter.page_count;
              let progressText: string | null;
              if (progress && completed) {
                progressText = pageCount > 0 ? `${pageCount}/${pageCount} pages` : "Read";
              } else if (progress && reading) {
                progressText =
                  pageCount > 0 ? `${progress.page}/${pageCount} pages` : `Page ${progress.page}`;
              } else {
                progressText = pageCount > 0 ? `${pageCount} pages` : null;
              }
              return (
                <div
                  key={chapter.id}
                  className={cn(
                    "flex flex-wrap items-center justify-between gap-3 px-2 py-3 transition-colors first:pt-0 hover:bg-surface-2/60",
                    completed && "bg-void/40",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div>
                      <p className={cn("font-medium text-fg", completed && "text-fg/50")}>
                        {label.primary}
                      </p>
                      {label.secondary != null && (
                        <p className={cn("text-sm text-fg/80", completed && "text-fg/40")}>
                          {label.secondary}
                        </p>
                      )}
                      {progressText != null && (
                        <p className={cn("text-sm", reading ? "text-primary" : "text-muted")}>
                          {progressText}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link
                      href={sourceReaderChapterPath(sourceId, seriesId, chapter.id)}
                      onMouseEnter={() => prefetchOnIntent(chapter.id)}
                      onMouseLeave={cancelPrefetchIntent}
                      onFocus={() => prefetchOnIntent(chapter.id)}
                      onBlur={cancelPrefetchIntent}
                    >
                      <Button variant="ghost" size="sm">
                        Read
                      </Button>
                    </Link>
                  </div>
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}
