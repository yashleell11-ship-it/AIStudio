"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  BookOpen,
  FolderOpen,
  Plus,
  Search,
  SlidersHorizontal,
  TriangleAlert,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  useCollections,
  useCreateCollection,
} from "@/features/library/hooks";
import type { Collection } from "@/features/library/types";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/cn";

type CollectionSort = "name" | "series" | "recent";

function collectionInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return "?";
  }
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase();
  }
  return `${words[0][0]}${words[1][0]}`.toUpperCase();
}

function sortCollections(items: Collection[], sort: CollectionSort): Collection[] {
  const next = [...items];
  switch (sort) {
    case "series":
      return next.sort((a, b) => b.series_count - a.series_count || a.name.localeCompare(b.name));
    case "recent":
      return next.sort((a, b) => b.id - a.id);
    default:
      return next.sort((a, b) => a.name.localeCompare(b.name));
  }
}

function CollectionBannerCard({ collection }: { collection: Collection }) {
  return (
    <Link
      href={`/library/collections/${collection.id}`}
      className="group block"
    >
      <article className="relative overflow-hidden rounded-2xl transition-all duration-300 hover:scale-[1.01] hover:shadow-glow">
        <div className="relative aspect-[21/9] min-h-[140px] w-full bg-surface-2 sm:aspect-[24/9]">
          {collection.cover_url ? (
            <Image
              src={collection.cover_url}
              alt=""
              fill
              className="object-cover transition-transform duration-500 group-hover:scale-105"
              sizes="(max-width: 768px) 100vw, 800px"
              unoptimized
            />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-br from-accent/40 via-panel to-primary/20" />
          )}
          <div className="absolute inset-0 bg-gradient-to-r from-void/95 via-void/70 to-void/30" />
          <div className="absolute inset-0 bg-gradient-to-t from-void/80 via-transparent to-transparent" />

          {!collection.cover_url && (
            <div className="absolute right-6 top-1/2 hidden -translate-y-1/2 font-display text-6xl tracking-widest text-white/10 sm:block">
              {collectionInitials(collection.name)}
            </div>
          )}

          <div className="absolute inset-0 flex flex-col justify-end p-5 sm:p-6">
            <h3 className="text-xl font-bold text-white transition-colors group-hover:text-primary sm:text-2xl">
              {collection.name}
            </h3>
            {collection.description && (
              <p className="mt-1 line-clamp-1 max-w-xl text-sm text-white/70">
                {collection.description}
              </p>
            )}
            <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-white/60">
              <BookOpen className="size-3.5" aria-hidden />
              {collection.series_count} series
            </p>
          </div>
        </div>
      </article>
    </Link>
  );
}

function CollectionsSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading collections">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="aspect-[21/9] min-h-[140px] animate-pulse rounded-2xl bg-surface-2" />
      ))}
    </div>
  );
}

export function CollectionsView() {
  const collectionsQuery = useCollections();
  const createCollection = useCreateCollection();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<CollectionSort>("name");
  const [sortOpen, setSortOpen] = useState(false);

  const collections = collectionsQuery.data ?? [];
  const viewState = resolveViewState({
    isLoading: collectionsQuery.isLoading,
    error: collectionsQuery.error,
    isEmpty: collections.length === 0,
  });

  const filteredCollections = useMemo(() => {
    const data = collectionsQuery.data ?? [];
    const query = search.trim().toLowerCase();
    const filtered = query
      ? data.filter(
          (collection) =>
            collection.name.toLowerCase().includes(query) ||
            (collection.description?.toLowerCase().includes(query) ?? false),
        )
      : data;
    return sortCollections(filtered, sort);
  }, [collectionsQuery.data, search, sort]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    try {
      await createCollection.mutateAsync({
        name: name.trim(),
        description: description.trim() || undefined,
      });
      setName("");
      setDescription("");
      setDialogOpen(false);
    } catch {
      // Error surfaced via mutation state
    }
  };

  const sortLabel =
    sort === "series" ? "Most series" : sort === "recent" ? "Recently created" : "Name A–Z";

  return (
    <div className="min-h-full bg-bg px-6 py-6 md:px-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="font-display text-4xl tracking-wide text-fg">Collections</h1>
            <p className="mt-1 text-sm text-muted">
              {collectionsQuery.data
                ? `${collectionsQuery.data.length} collection${collectionsQuery.data.length === 1 ? "" : "s"}`
                : "Organize your library into custom collections."}
            </p>
          </div>
          <Button onClick={() => setDialogOpen(true)} className="gap-2 shadow-glow">
            <Plus className="size-4" aria-hidden />
            New Collection
          </Button>
        </div>

        {collectionsQuery.data && collectionsQuery.data.length > 0 && (
          <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
                aria-hidden
              />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search collections…"
                className="border-border/50 bg-white/[0.03] pl-10"
              />
            </div>
            <div className="relative">
              <Button
                variant="secondary"
                onClick={() => setSortOpen((open) => !open)}
                className="w-full gap-2 sm:w-auto"
              >
                <SlidersHorizontal className="size-4" aria-hidden />
                {sortLabel}
              </Button>
              {sortOpen && (
                <>
                  <button
                    type="button"
                    aria-label="Close sort menu"
                    className="fixed inset-0 z-10"
                    onClick={() => setSortOpen(false)}
                  />
                  <div className="absolute right-0 z-20 mt-2 w-48 overflow-hidden rounded-xl border border-border bg-panel shadow-xl">
                    {(
                      [
                        ["name", "Name A–Z"],
                        ["series", "Most series"],
                        ["recent", "Recently created"],
                      ] as const
                    ).map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => {
                          setSort(value);
                          setSortOpen(false);
                        }}
                        className={cn(
                          "block w-full px-4 py-2.5 text-left text-sm transition-colors hover:bg-white/5",
                          sort === value ? "text-primary" : "text-fg",
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {viewState === "loading" ? (
          <CollectionsSkeleton />
        ) : viewState === "offline" ? (
          <EmptyState
            tone="offline"
            icon={WifiOff}
            title="You're offline"
            description="Collections need a connection to load. Chapters you've downloaded still open with no connection at all."
            action={{ label: "Go to Downloads", href: "/downloads" }}
          />
        ) : viewState === "error" ? (
          <EmptyState
            tone="error"
            icon={TriangleAlert}
            title="Couldn't load collections"
            description={apiErrorMessage(collectionsQuery.error, "Something went wrong.")}
            action={{ label: "Try again", onClick: () => void collectionsQuery.refetch() }}
          />
        ) : viewState === "empty" ? (
          <EmptyState
            icon={FolderOpen}
            title="No collections yet"
            description="Create collections to group your series by theme, mood, or reading list."
            action={{
              label: "Create your first collection",
              icon: Plus,
              onClick: () => setDialogOpen(true),
            }}
          />
        ) : filteredCollections.length === 0 ? (
          <div className="glass-panel rounded-3xl border border-dashed border-border/50 p-12 text-center">
            <p className="text-lg font-medium text-fg">No collections match your search</p>
            <p className="mt-2 text-sm text-muted">Try a different term or clear the search.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredCollections.map((collection) => (
              <CollectionBannerCard key={collection.id} collection={collection} />
            ))}
          </div>
        )}

        <Dialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          title="New Collection"
          className="glass-panel max-w-md border-border/50"
        >
          <div className="space-y-4">
            <div>
              <label htmlFor="collection-name" className="mb-1.5 block text-sm font-medium text-fg">
                Name
              </label>
              <Input
                id="collection-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Reading List"
                className="border-border/50 bg-white/[0.03]"
              />
            </div>
            <div>
              <label
                htmlFor="collection-description"
                className="mb-1.5 block text-sm font-medium text-fg"
              >
                Description
              </label>
              <Input
                id="collection-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description"
                className="border-border/50 bg-white/[0.03]"
              />
            </div>
            {createCollection.error && (
              <p className="text-sm text-danger">
                {createCollection.error instanceof ApiError
                  ? createCollection.error.message
                  : "Failed to create collection."}
              </p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!name.trim() || createCollection.isPending}
                className="min-w-[100px]"
              >
                {createCollection.isPending ? "Creating…" : "Create"}
              </Button>
            </div>
          </div>
        </Dialog>
      </div>
    </div>
  );
}
