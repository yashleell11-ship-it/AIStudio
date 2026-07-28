"use client";

import { CloudOff, Library, RefreshCw, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SourceLogo } from "@/features/sources/components/SourceLogo";
import { isLocalSearchGroup, searchGroupNote } from "@/features/sources/global-search";
import type { GlobalSearchGroup } from "@/features/sources/types";
import { cn } from "@/lib/cn";
import { GlobalSearchResultCard } from "./GlobalSearchResultCard";
import { SearchResultCardSkeleton } from "./SearchResultCard";

interface GlobalSearchGroupSectionProps {
  group: GlobalSearchGroup;
  /** A single-source retry is in flight for this section. */
  isRetrying?: boolean;
  /** Omitted for the local library group — there is no remote call to retry. */
  onRetry?: () => void;
}

/**
 * One source's slice of a federated search.
 *
 * A section per source (rather than one merged list) is what makes a partial
 * failure legible: with ~50 connectors some are always down, and a flat list
 * turns "3 sources timed out" into "not many results". Each section owns its
 * own empty, error and retry state.
 */
export function GlobalSearchGroupSection({
  group,
  isRetrying = false,
  onRetry,
}: GlobalSearchGroupSectionProps) {
  const isLocal = isLocalSearchGroup(group);
  const note = searchGroupNote(group);
  const failed = group.status === "error";

  return (
    <section className="mb-8">
      <div className="mb-3 flex items-center gap-2">
        {isLocal ? (
          <span className="flex size-7 items-center justify-center rounded-lg border border-primary/30 bg-primary/10 text-primary">
            <Library className="size-4" aria-hidden />
          </span>
        ) : (
          <SourceLogo
            id={group.source ?? ""}
            name={group.source_name}
            iconUrl={group.icon_url}
            size={28}
          />
        )}
        <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-fg">
          {group.source_name}
        </h3>
        {group.items.length > 0 ? (
          <span className="rounded-full border border-border/50 bg-white/[0.06] px-2 py-0.5 text-xs font-semibold tabular-nums text-muted">
            {group.total}
          </span>
        ) : null}
      </div>

      {isRetrying ? (
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, index) => (
            <SearchResultCardSkeleton key={index} />
          ))}
        </div>
      ) : note ? (
        <div
          className={cn(
            "flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-sm",
            failed
              ? "border-danger/30 bg-danger/10 text-danger"
              : "border-border/50 bg-white/[0.02] text-muted",
          )}
        >
          {failed ? (
            <CloudOff className="size-4 shrink-0" aria-hidden />
          ) : (
            <SearchX className="size-4 shrink-0" aria-hidden />
          )}
          <span className="min-w-0 flex-1">{note}</span>
          {onRetry ? (
            <Button variant="secondary" size="sm" onClick={onRetry}>
              <RefreshCw className="size-3.5" aria-hidden />
              Retry
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="space-y-3">
          {group.items.map((item) => (
            <GlobalSearchResultCard
              key={`${item.kind}:${item.source ?? "local"}:${item.series_id}`}
              item={item}
              showSourceBadge={false}
            />
          ))}
        </div>
      )}
    </section>
  );
}
