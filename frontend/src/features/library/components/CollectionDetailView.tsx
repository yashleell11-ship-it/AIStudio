"use client";

import Link from "next/link";
import Image from "next/image";
import { useMemo, useState } from "react";
import { ArrowLeft, BookOpen, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { libraryCoverUrl } from "@/features/library/api";
import {
  useAddSeriesToCollection,
  useCollection,
  useDeleteCollection,
  useSeriesList,
} from "@/features/library/hooks";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/cn";
import { SeriesGrid } from "./SeriesGrid";
import type { FollowedSeries } from "../types";

interface CollectionDetailViewProps {
  collectionId: number;
}

function DetailSkeleton() {
  return (
    <div
      className="min-h-full bg-bg px-6 py-6 md:px-10"
      aria-busy="true"
      aria-label="Loading collection"
    >
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 h-4 w-40 animate-pulse rounded bg-surface-2" />
        <div className="mb-8 h-48 animate-pulse rounded-2xl bg-surface-2" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="aspect-[2/3] animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function CollectionDetailView({ collectionId }: CollectionDetailViewProps) {
  const collectionQuery = useCollection(collectionId);
  const allSeriesQuery = useSeriesList({ page: 1, per_page: 200, sort: "title" });
  const addSeries = useAddSeriesToCollection();
  const deleteCollection = useDeleteCollection();
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addSearch, setAddSearch] = useState("");

  const collection = collectionQuery.data;
  const allSeries = useMemo(
    () => allSeriesQuery.data?.items ?? [],
    [allSeriesQuery.data],
  );

  // Collection membership is `(source_id, series_key)` refs; resolve them
  // against the followed set for cover + title.
  const memberKeys = useMemo(() => {
    const set = new Set<string>();
    for (const ref of collection?.series ?? []) {
      set.add(`${ref.source_id}:${ref.series_key}`);
    }
    return set;
  }, [collection]);

  const members = useMemo<FollowedSeries[]>(
    () => allSeries.filter((s) => memberKeys.has(`${s.source_id}:${s.series_key}`)),
    [allSeries, memberKeys],
  );

  if (collectionQuery.isLoading) {
    return <DetailSkeleton />;
  }

  if (collectionQuery.error || !collection) {
    const message =
      collectionQuery.error instanceof ApiError
        ? collectionQuery.error.message
        : "Failed to load collection.";
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 p-6 text-center">
        <p className="text-danger">{message}</p>
        <Link href="/library/collections">
          <Button variant="secondary" className="gap-2">
            <ArrowLeft className="size-4" aria-hidden />
            Back to collections
          </Button>
        </Link>
      </div>
    );
  }

  const availableSeries = allSeries.filter(
    (series) => !memberKeys.has(`${series.source_id}:${series.series_key}`),
  );
  const filteredAvailable = addSearch.trim()
    ? availableSeries.filter((series) =>
        series.title.toLowerCase().includes(addSearch.toLowerCase()),
      )
    : availableSeries;

  return (
    <div className="min-h-full bg-bg">
      <div className="relative overflow-hidden border-b border-border/50">
        <div className="absolute inset-0">
          {collection.cover_url ? (
            <Image
              src={collection.cover_url}
              alt=""
              fill
              className="object-cover opacity-40 blur-2xl"
              sizes="100vw"
              unoptimized
            />
          ) : (
            <div className="h-full w-full bg-gradient-to-br from-accent/30 via-void to-primary/20" />
          )}
          <div className="absolute inset-0 bg-gradient-to-b from-void/40 via-void/80 to-bg" />
        </div>

        <div className="relative mx-auto max-w-7xl px-6 py-6 md:px-10">
          <Link
            href="/library/collections"
            className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-primary"
          >
            <ArrowLeft className="size-3.5" aria-hidden />
            Back to collections
          </Link>

          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="min-w-0">
              <h1 className="font-display text-4xl tracking-wide text-fg">
                {collection.name}
              </h1>
              {collection.description && (
                <p className="mt-2 max-w-2xl text-sm text-muted">
                  {collection.description}
                </p>
              )}
              <p className="mt-3 inline-flex items-center gap-1.5 text-sm text-muted">
                <BookOpen className="size-4 text-primary" aria-hidden />
                {collection.series.length} series
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() => setShowAddDialog(true)}
                className="gap-2"
              >
                <Plus className="size-4" aria-hidden />
                Add Series
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  if (confirm("Delete this collection? Series will not be removed.")) {
                    deleteCollection.mutate(collectionId);
                  }
                }}
                className="gap-2"
              >
                <Trash2 className="size-4" aria-hidden />
                Delete
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-6 py-8 md:px-10">
        {collection.series.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="This collection is empty"
            description="Add series from your library to start building this collection."
            action={{
              label: "Add series",
              icon: Plus,
              onClick: () => setShowAddDialog(true),
            }}
          />
        ) : (
          <SeriesGrid items={members} isLoading={allSeriesQuery.isLoading} />
        )}
      </div>

      <Dialog
        open={showAddDialog}
        onClose={() => {
          setShowAddDialog(false);
          setAddSearch("");
        }}
        title="Add Series to Collection"
        className="glass-panel max-w-lg border-border/50"
      >
        <div className="space-y-4">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
              aria-hidden
            />
            <Input
              value={addSearch}
              onChange={(e) => setAddSearch(e.target.value)}
              placeholder="Search series…"
              className="border-border/50 bg-white/[0.03] pl-10"
            />
          </div>
          <div className="max-h-[400px] space-y-2 overflow-y-auto pr-1">
            {allSeriesQuery.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div key={index} className="h-14 animate-pulse rounded-xl bg-surface-2" />
                ))}
              </div>
            ) : filteredAvailable.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted">No series available.</p>
            ) : (
              filteredAvailable.map((series) => (
                <button
                  key={series.id}
                  type="button"
                  onClick={() => {
                    addSeries.mutate(
                      {
                        collectionId,
                        ref: {
                          sourceId: series.source_id,
                          seriesKey: series.series_key,
                        },
                      },
                      {
                        onSuccess: () => {
                          setShowAddDialog(false);
                          setAddSearch("");
                        },
                      },
                    );
                  }}
                  disabled={addSeries.isPending}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl border border-border/50 bg-white/[0.02] px-3 py-2.5 text-left transition-all duration-200",
                    "hover:border-primary/30 hover:bg-primary/5",
                    addSeries.isPending && "opacity-60",
                  )}
                >
                  <div className="relative h-12 w-8 shrink-0 overflow-hidden rounded-lg bg-surface-2 ring-1 ring-white/10">
                    <Image
                      src={libraryCoverUrl(series.cover_url, "32px")}
                      alt={series.title}
                      fill
                      className="object-cover"
                      sizes="32px"
                      unoptimized
                    />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-fg">{series.title}</p>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      </Dialog>
    </div>
  );
}
