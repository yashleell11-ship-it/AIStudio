"use client";

import Link from "next/link";
import { ApiError } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSources } from "../hooks";

export function SourcesListView() {
  const sourcesQuery = useSources();

  if (sourcesQuery.isLoading) {
    return (
      <div className="page-shell">
        <div className="page-container">
          <div className="mb-8">
            <div className="h-10 w-32 animate-pulse rounded-lg bg-surface-2" />
            <div className="mt-2 h-4 w-72 animate-pulse rounded bg-surface-2" />
          </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="h-32 animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
        </div>
      </div>
    );
  }

  if (sourcesQuery.error) {
    const message =
      sourcesQuery.error instanceof ApiError
        ? sourcesQuery.error.message
        : "Failed to load sources.";
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="text-danger">{message}</p>
        <Button variant="secondary" onClick={() => sourcesQuery.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  const sources = sourcesQuery.data ?? [];

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8">
          <h1 className="page-title">Sources</h1>
          <p className="page-subtitle">Browse online catalogs from installed source connectors.</p>
        </div>

      {sources.length === 0 ? (
        <div className="empty-state">
          <p className="text-lg font-medium text-fg">No sources installed</p>
          <p className="mt-2 text-sm text-muted">
            Source connectors will appear here when registered with the backend.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sources.map((source) => (
            <Link key={source.id} href={`/sources/${source.id}`}>
              <Card className="h-full transition-colors hover:border-primary/40">
                <CardHeader>
                  <CardTitle>{source.name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="line-clamp-3 text-sm text-muted">{source.description}</p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
      </div>
    </div>
  );
}
