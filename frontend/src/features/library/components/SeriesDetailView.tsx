"use client";

import Image from "next/image";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { ApiError } from "@/types/api";
import { SeriesCard } from "./SeriesCard";

interface SeriesDetailViewProps {
  seriesId: number;
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
      prefetchReaderChapter(queryClient, chapter.id);
    }
  }, [queryClient, series]);

  if (seriesQuery.isLoading) {
    return (
      <div className="p-6" aria-busy="true" aria-label="Loading series">
        <div className="mb-6 h-4 w-32 animate-pulse rounded bg-surface-2" />
        <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
          <div className="aspect-[2/3] animate-pulse rounded-xl bg-surface-2" />
          <div className="space-y-4">
            <div className="h-8 w-2/3 animate-pulse rounded bg-surface-2" />
            <div className="h-4 w-full animate-pulse rounded bg-surface-2" />
            <div className="h-4 w-1/2 animate-pulse rounded bg-surface-2" />
            <div className="h-32 animate-pulse rounded-xl bg-surface-2" />
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
          className="mt-4 inline-flex h-10 items-center justify-center rounded-lg bg-surface-2 px-4 text-sm font-medium text-fg hover:bg-border"
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

  const metadata = metadataQuery.data;
  const similar = similarQuery.data ?? [];

  return (
    <div className="p-6">
      <div className="mb-6">
        <Link href="/library" className="text-sm text-muted hover:text-fg">
          ← Back to library
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <Card className="overflow-hidden">
          <div className="relative aspect-[2/3] w-full bg-surface-2">
            <Image
              src={coverUrl(series.id)}
              alt={series.title}
              fill
              className="object-cover"
              sizes="220px"
              unoptimized
            />
          </div>
        </Card>

        <div>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-fg">{series.title}</h1>
              {series.original_title && (
                <p className="mt-1 text-sm text-muted italic">{series.original_title}</p>
              )}
            </div>
            <Button
              variant={series.is_favorite ? "primary" : "secondary"}
              onClick={() => toggleFavorite.mutate(series.id)}
              aria-label={series.is_favorite ? "Remove from favorites" : "Add to favorites"}
            >
              {series.is_favorite ? "★ Favorite" : "☆ Add Favorite"}
            </Button>
          </div>

          {series.author && <p className="mt-2 text-muted">{series.author}</p>}
          {series.artist && (
            <p className="text-sm text-muted">Artist: {series.artist}</p>
          )}
          <p className="mt-2 text-sm text-muted">
            {series.chapter_count} chapters · {series.page_count} pages
            {series.year && ` · ${series.year}`}
            {series.language && ` · ${series.language.toUpperCase()}`}
          </p>
          {series.reading_status && (
            <Badge variant={series.reading_status === "reading" ? "primary" : "default"} className="mt-2">
              {series.reading_status}
            </Badge>
          )}

          {continueHref && (
            <Link
              href={continueHref}
              className="mt-4 inline-flex h-10 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-fg hover:bg-primary-hover"
            >
              {progress ? "Continue Reading" : "Start Reading"}
            </Link>
          )}

          {/* Tags */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {series.tags.map((tag) => (
              <Badge
                key={tag.id}
                variant="default"
                className="cursor-pointer"
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
            >
              + Tag
            </Button>
          </div>
          {showTagPicker && tagsQuery.data && (
            <div className="mt-2 flex flex-wrap gap-2">
              {tagsQuery.data
                .filter((t) => !series.tags.some((st) => st.id === t.id))
                .map((tag) => (
                  <Badge
                    key={tag.id}
                    variant="default"
                    className="cursor-pointer hover:bg-primary/15"
                    onClick={() => {
                      addTag.mutate({ seriesId: series.id, tagId: tag.id });
                      setShowTagPicker(false);
                    }}
                  >
                    + {tag.name}
                  </Badge>
                ))}
            </div>
          )}

          {/* Collections */}
          {series.collections.length > 0 && (
            <div className="mt-2 text-sm text-muted">
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
          )}

          {/* Description */}
          {series.description && (
            <p className="mt-4 text-sm leading-relaxed text-fg/80">
              {series.description}
            </p>
          )}
        </div>
      </div>

      {/* Metadata Quality */}
      {metadata && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              Metadata Quality
              <span className="text-sm font-normal text-muted">
                {metadata.score}/100
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Progress value={metadata.score} className="mb-3" />
            {metadata.suggestions.length > 0 && (
              <div className="space-y-1">
                {metadata.suggestions.map((s) => (
                  <p key={s} className="text-sm text-muted">• {s}</p>
                ))}
              </div>
            )}
            {metadata.suggestions.length === 0 && (
              <p className="text-sm text-success">All metadata fields complete!</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Chapters */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Chapters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {series.chapters.length === 0 ? (
            <p className="text-sm text-muted">No chapters found for this series.</p>
          ) : (
            series.chapters.map((chapter) => {
              const isCurrent = progress?.chapter_id === chapter.id;
              return (
                <Link
                  key={chapter.id}
                  href={`/reader/${series.id}/${chapter.id}`}
                  onMouseEnter={() => prefetchChapter(chapter.id)}
                  onFocus={() => prefetchChapter(chapter.id)}
                  className="flex items-center justify-between rounded-lg border border-border px-4 py-3 transition-colors hover:border-primary/40 hover:bg-surface-2"
                >
                  <div>
                    <p className="font-medium text-fg">{chapter.title}</p>
                    <p className="text-sm text-muted">{chapter.page_count} pages</p>
                  </div>
                  {isCurrent && <Badge variant="primary">In progress</Badge>}
                </Link>
              );
            })
          )}
        </CardContent>
      </Card>

      {/* Similar Series */}
      {similar.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
            Similar Series
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {similar.map((s) => (
              <SeriesCard key={s.id} series={s} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
