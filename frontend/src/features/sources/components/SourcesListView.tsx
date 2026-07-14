"use client";

import Link from "next/link";
import { ApiError } from "@/types/api";
import { Button } from "@/components/ui/button";
import { useSources } from "../hooks";
import { SourceLogo } from "./SourceLogo";

export function SourcesListView() {
  const sourcesQuery = useSources();

  if (sourcesQuery.isLoading) {
    return (
      <div className="page-shell">
        <div className="page-container">
          <div className="mb-8">
            <div className="h-10 w-32 animate-pulse rounded-lg bg-surface-2" />
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {Array.from({ length: 12 }).map((_, index) => (
              <div
                key={index}
                className="flex flex-col items-center gap-3 rounded-3xl border border-border bg-surface p-5"
              >
                <div className="aspect-square w-full max-w-[72px] animate-pulse rounded-2xl bg-surface-2" />
                <div className="h-3 w-16 animate-pulse rounded bg-surface-2" />
              </div>
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
        </div>

        {sources.length === 0 ? (
          <div className="empty-state">
            <p className="text-lg font-medium text-fg">No sources installed</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {sources.map((source) => (
              <Link
                key={source.id}
                href={`/sources/${source.id}`}
                className="group flex flex-col items-center gap-3 rounded-3xl border border-border bg-surface p-5 text-center transition duration-200 hover:scale-105 hover:border-primary/40"
              >
                <SourceLogo
                  id={source.id}
                  name={source.name}
                  iconUrl={source.icon_url}
                  size={72}
                  className="bg-surface-2/80"
                />
                <p className="line-clamp-2 w-full font-display text-sm leading-snug text-fg">
                  {source.name}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
