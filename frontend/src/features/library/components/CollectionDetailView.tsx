"use client";

import Link from "next/link";
import Image from "next/image";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { coverUrl } from "@/features/library/api";
import {
  useAddSeriesToCollection,
  useCollection,
  useDeleteCollection,
  useSeriesList,
} from "@/features/library/hooks";
import { ApiError } from "@/types/api";
import { SeriesGrid } from "./SeriesGrid";

interface CollectionDetailViewProps {
  collectionId: number;
}

export function CollectionDetailView({ collectionId }: CollectionDetailViewProps) {
  const collectionQuery = useCollection(collectionId);
  const allSeriesQuery = useSeriesList({ page: 1, per_page: 200 });
  const addSeries = useAddSeriesToCollection();
  const deleteCollection = useDeleteCollection();
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addSearch, setAddSearch] = useState("");

  const collection = collectionQuery.data;

  if (collectionQuery.isLoading) {
    return (
      <div className="p-6" aria-busy="true" aria-label="Loading collection">
        <div className="mb-6 h-4 w-40 animate-pulse rounded bg-surface-2" />
        <div className="mb-6 h-8 w-64 animate-pulse rounded bg-surface-2" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="aspect-[2/3] animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      </div>
    );
  }

  if (collectionQuery.error || !collection) {
    const message =
      collectionQuery.error instanceof ApiError
        ? collectionQuery.error.message
        : "Failed to load collection.";
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="text-danger">{message}</p>
        <Link
          href="/library/collections"
          className="mt-4 inline-flex h-10 items-center justify-center rounded-lg bg-surface-2 px-4 text-sm font-medium text-fg hover:bg-border"
        >
          Back to collections
        </Link>
      </div>
    );
  }

  const availableSeries =
    allSeriesQuery.data?.items.filter(
      (s) => !collection.series.items.some((cs) => cs.id === s.id),
    ) ?? [];

  const filteredAvailable = addSearch.trim()
    ? availableSeries.filter(
        (s) =>
          s.title.toLowerCase().includes(addSearch.toLowerCase()) ||
          (s.author?.toLowerCase().includes(addSearch.toLowerCase()) ?? false),
      )
    : availableSeries;

  return (
    <div className="p-6">
      <div className="mb-6">
        <Link href="/library/collections" className="text-sm text-muted hover:text-fg">
          ← Back to collections
        </Link>
      </div>

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-fg">{collection.name}</h1>
          {collection.description && (
            <p className="mt-1 text-sm text-muted">{collection.description}</p>
          )}
          <p className="mt-2 text-sm text-muted">
            {collection.series.total} series
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={() => setShowAddDialog(true)}
          >
            Add Series
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              if (confirm("Delete this collection? Series will not be removed.")) {
                deleteCollection.mutate(collectionId);
              }
            }}
          >
            Delete
          </Button>
        </div>
      </div>

      <SeriesGrid
        items={collection.series.items}
        isLoading={collectionQuery.isLoading}
      />

      {/* Add Series Dialog */}
      <Dialog
        open={showAddDialog}
        onClose={() => setShowAddDialog(false)}
        title="Add Series to Collection"
      >
        <div className="space-y-4">
          <input
            type="text"
            value={addSearch}
            onChange={(e) => setAddSearch(e.target.value)}
            placeholder="Search series…"
            className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-fg"
          />
          <div className="max-h-[400px] space-y-2 overflow-y-auto">
            {allSeriesQuery.isLoading ? (
              <p className="text-sm text-muted">Loading…</p>
            ) : filteredAvailable.length === 0 ? (
              <p className="text-sm text-muted">No series available.</p>
            ) : (
              filteredAvailable.map((series) => (
                <button
                  key={series.id}
                  type="button"
                  onClick={() => {
                    addSeries.mutate(
                      { collectionId, seriesId: series.id },
                      {
                        onSuccess: () => setShowAddDialog(false),
                      },
                    );
                  }}
                  className="flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2 text-left transition-colors hover:bg-surface-2"
                >
                  <div className="relative h-12 w-8 shrink-0 overflow-hidden rounded bg-surface-2">
                    <Image
                      src={coverUrl(series.id)}
                      alt={series.title}
                      fill
                      className="object-cover"
                      sizes="32px"
                      unoptimized
                    />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-fg">
                      {series.title}
                    </p>
                    {series.author && (
                      <p className="truncate text-xs text-muted">{series.author}</p>
                    )}
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
