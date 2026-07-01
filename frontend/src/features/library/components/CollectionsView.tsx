"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  useCollections,
  useCreateCollection,
} from "@/features/library/hooks";
import { ApiError } from "@/types/api";

export function CollectionsView() {
  const collectionsQuery = useCollections();
  const createCollection = useCreateCollection();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const errorMessage =
    collectionsQuery.error instanceof ApiError
      ? collectionsQuery.error.message
      : collectionsQuery.error
        ? "Failed to load collections."
        : null;

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

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-fg">Collections</h1>
          <p className="mt-1 text-sm text-muted">
            Organize your library into custom collections.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>New Collection</Button>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {errorMessage}
        </div>
      )}

      {collectionsQuery.isLoading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="aspect-[2/3] animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      ) : collectionsQuery.data && collectionsQuery.data.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-surface p-12 text-center">
          <p className="text-lg font-medium text-fg">No collections yet</p>
          <p className="mt-2 text-sm text-muted">
            Create collections to group your series by theme, mood, or reading list.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {collectionsQuery.data?.map((collection) => (
            <Link
              key={collection.id}
              href={`/library/collections/${collection.id}`}
              className="group"
            >
              <Card className="overflow-hidden transition-colors hover:border-primary/40">
                <div className="relative aspect-[2/3] w-full bg-surface-2">
                  {collection.cover_path ? (
                    <Image
                      src={collection.cover_path}
                      alt={collection.name}
                      fill
                      className="object-cover"
                      sizes="200px"
                      unoptimized
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-xs text-muted">
                      No cover
                    </div>
                  )}
                </div>
                <div className="p-3">
                  <h3 className="font-medium text-fg">{collection.name}</h3>
                  <p className="mt-1 text-xs text-muted">
                    {collection.series_count} series
                  </p>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title="New Collection">
        <div className="space-y-4">
          <div>
            <label htmlFor="collection-name" className="mb-1 block text-sm font-medium text-fg">
              Name
            </label>
            <Input
              id="collection-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Reading List"
            />
          </div>
          <div>
            <label
              htmlFor="collection-description"
              className="mb-1 block text-sm font-medium text-fg"
            >
              Description
            </label>
            <Input
              id="collection-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
            />
          </div>
          {createCollection.error && (
            <p className="text-sm text-danger">
              {createCollection.error instanceof ApiError
                ? createCollection.error.message
                : "Failed to create collection."}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!name.trim() || createCollection.isPending}
            >
              {createCollection.isPending ? "Creating…" : "Create"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
