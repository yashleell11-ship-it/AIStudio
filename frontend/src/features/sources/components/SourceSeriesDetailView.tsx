"use client";

import Image from "next/image";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useQueueChapters, useQueueSeries } from "@/features/downloads/hooks";
import {
  useFollowedTracker,
  useFollowSeries,
  useUnfollowTracker,
} from "@/features/updates/hooks";
import { ApiError } from "@/types/api";
import { sourceImageUrl } from "../api";
import { chapterLabel } from "../chapter-label";
import {
  prefetchSourceReaderChapter,
  sourceReaderChapterPath,
  useSourceChapters,
  useSourceSeriesDetail,
} from "../hooks";

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
  const queueChapters = useQueueChapters();
  const queueSeries = useQueueSeries();
  const followedTracker = useFollowedTracker(sourceId, seriesId);
  const followMutation = useFollowSeries();
  const unfollowMutation = useUnfollowTracker();
  const queryClient = useQueryClient();
  const [selectedChapterIds, setSelectedChapterIds] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState<string | null>(null);

  const series = seriesQuery.data;
  const chapters = useMemo(() => chaptersQuery.data ?? [], [chaptersQuery.data]);

  useEffect(() => {
    for (const chapter of chapters.slice(0, 5)) {
      prefetchSourceReaderChapter(queryClient, sourceId, seriesId, chapter.id);
    }
  }, [chapters, queryClient, seriesId, sourceId]);

  const chapterTitleMap = useMemo(
    () => Object.fromEntries(chapters.map((chapter) => [chapter.id, chapter.title])),
    [chapters],
  );

  if (seriesQuery.isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-muted">
        Loading series…
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
        <Link href={`/sources/${sourceId}`} className="text-sm text-muted hover:text-fg">
          Back to source
        </Link>
      </div>
    );
  }

  const firstChapter = chapters[0];
  const readOnlineHref = firstChapter
    ? sourceReaderChapterPath(sourceId, seriesId, firstChapter.id)
    : null;

  const prefetchChapter = (chapterId: string) => {
    prefetchSourceReaderChapter(queryClient, sourceId, seriesId, chapterId);
  };

  const toggleChapter = (chapterId: string) => {
    setSelectedChapterIds((current) => {
      const next = new Set(current);
      if (next.has(chapterId)) {
        next.delete(chapterId);
      } else {
        next.add(chapterId);
      }
      return next;
    });
  };

  const queueDownload = async (chapterIds: string[], label: string) => {
    if (chapterIds.length === 0) {
      setFeedback("Select at least one chapter.");
      return;
    }
    setFeedback(null);
    try {
      const result = await queueChapters.mutateAsync({
        source_id: sourceId,
        series_id: seriesId,
        chapter_ids: chapterIds,
        series_title: series.title,
        chapter_titles: chapterTitleMap,
      });
      const queued = result.queued.length;
      const skipped = result.skipped.length;
      if (queued === 0 && skipped > 0) {
        setFeedback(`${label}: all selected chapters are already queued or downloaded.`);
      } else {
        setFeedback(
          `${label}: queued ${queued} chapter${queued === 1 ? "" : "s"}` +
            (skipped > 0 ? `, skipped ${skipped} duplicate${skipped === 1 ? "" : "s"}` : "") +
            ".",
        );
      }
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Failed to queue download.");
    }
  };

  const downloadSeries = async () => {
    setFeedback(null);
    try {
      const result = await queueSeries.mutateAsync({
        source_id: sourceId,
        series_id: seriesId,
      });
      setFeedback(
        `Queued ${result.queued.length} chapters` +
          (result.skipped.length > 0 ? `, skipped ${result.skipped.length} duplicates` : "") +
          ".",
      );
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Failed to queue series download.");
    }
  };

  const toggleFollow = async () => {
    setFeedback(null);
    try {
      if (followedTracker) {
        await unfollowMutation.mutateAsync(followedTracker.id);
        setFeedback(`Unfollowed ${series.title}.`);
      } else {
        await followMutation.mutateAsync({
          source: sourceId,
          series_id: seriesId,
          series_title: series.title,
        });
        setFeedback(`Following ${series.title}. New chapters will notify you.`);
      }
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Failed to update follow status.");
    }
  };

  const downloadBusy = queueChapters.isPending || queueSeries.isPending;
  const followBusy = followMutation.isPending || unfollowMutation.isPending;
  const isFollowed = Boolean(followedTracker);

  return (
    <div className="p-6">
      <div className="mb-6">
        <Link href={`/sources/${sourceId}`} className="text-sm text-muted hover:text-fg">
          ← Back to source
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <Card className="overflow-hidden">
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
          <h1 className="text-3xl font-bold text-fg">{series.title}</h1>
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
                <Badge key={genre} variant="default">
                  {genre}
                </Badge>
              ))}
            </div>
          )}
          {series.description && (
            <p className="mt-4 max-w-3xl text-sm leading-6 text-muted">{series.description}</p>
          )}

          <div className="mt-6 flex flex-wrap gap-2">
            {readOnlineHref && (
              <Link
                href={readOnlineHref}
                onMouseEnter={() => firstChapter && prefetchChapter(firstChapter.id)}
                onFocus={() => firstChapter && prefetchChapter(firstChapter.id)}
              >
                <Button>Read Online</Button>
              </Link>
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
            <Button variant="secondary" disabled={downloadBusy || chapters.length === 0} onClick={downloadSeries}>
              Download Entire Series
            </Button>
            <Button
              variant="secondary"
              disabled={downloadBusy || selectedChapterIds.size === 0}
              onClick={() =>
                queueDownload(Array.from(selectedChapterIds), "Download selected")
              }
            >
              Download Selected Chapters
            </Button>
            <Link href="/downloads">
              <Button variant="ghost">View Downloads</Button>
            </Link>
          </div>
          {feedback && <p className="mt-3 text-sm text-muted">{feedback}</p>}
        </div>
      </div>

      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Chapters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {chaptersQuery.isLoading ? (
            <p className="text-sm text-muted">Loading chapters…</p>
          ) : chaptersQuery.error ? (
            <div className="flex flex-col gap-2">
              <p className="text-sm text-danger">
                {chaptersQuery.error instanceof ApiError
                  ? chaptersQuery.error.message
                  : "Failed to load chapters."}
              </p>
              <Button variant="secondary" size="sm" onClick={() => chaptersQuery.refetch()}>
                Try again
              </Button>
            </div>
          ) : chapters.length === 0 ? (
            <p className="text-sm text-muted">No chapters available.</p>
          ) : (
            chapters.map((chapter) => {
              const selected = selectedChapterIds.has(chapter.id);
              const label = chapterLabel(chapter);
              return (
                <div
                  key={chapter.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border px-4 py-3 transition-colors hover:border-primary/40 hover:bg-surface-2"
                >
                  <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3">
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleChapter(chapter.id)}
                      className="h-4 w-4 rounded border-border"
                    />
                    <div>
                      <p className="font-medium text-fg">{label.primary}</p>
                      {label.secondary != null && (
                        <p className="text-sm text-fg/80">{label.secondary}</p>
                      )}
                      <p className="text-sm text-muted">{chapter.page_count} pages</p>
                    </div>
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={downloadBusy}
                      onClick={() => queueDownload([chapter.id], "Download chapter")}
                    >
                      Download Chapter
                    </Button>
                    <Link
                      href={sourceReaderChapterPath(sourceId, seriesId, chapter.id)}
                      onMouseEnter={() => prefetchChapter(chapter.id)}
                      onFocus={() => prefetchChapter(chapter.id)}
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
