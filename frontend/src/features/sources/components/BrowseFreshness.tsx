"use client";

import { useEffect, useState } from "react";
import { CloudOff, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { describeBrowseFreshness } from "../browse-freshness";
import type { SourceBrowseCache } from "../types";

interface BrowseFreshnessProps {
  cache: SourceBrowseCache | null | undefined;
  onRefresh: () => void;
  refreshing?: boolean;
}

/** The age only ever changes by minutes, so a slow tick keeps it honest. */
const TICK_MS = 30_000;

/**
 * "Updated 3 min ago" / "Saved copy · 5 h ago", plus the button that does
 * something about it.
 *
 * The server has always told the client how old a browse page is and whether
 * the source was reachable when it was fetched; until now the web client threw
 * that away, so a catalog served from a dead connector looked exactly like a
 * live one. Re-renders on a timer so the age does not freeze at whatever it
 * said when the grid painted.
 */
export function BrowseFreshness({ cache, onRefresh, refreshing }: BrowseFreshnessProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(timer);
  }, []);

  const freshness = describeBrowseFreshness(cache, now);
  if (!freshness) return null;

  const stale = freshness.tone === "stale";

  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        title={freshness.detail}
        className={cn(
          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
          stale
            ? "bg-warning/12 text-warning"
            : "bg-white/5 text-muted",
        )}
      >
        {stale ? <CloudOff className="size-3" aria-hidden /> : null}
        {freshness.label}
      </span>
      {/* Screen readers get the explanation the chip's tooltip carries. */}
      <span className="sr-only">{freshness.detail}</span>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onRefresh}
        disabled={refreshing}
        aria-label="Refresh this catalog from the source"
        title="Refresh this catalog from the source"
        className="h-7 gap-1 px-2 text-[11px] text-muted hover:text-primary"
      >
        <RefreshCw className={cn("size-3", refreshing && "animate-spin")} aria-hidden />
        {refreshing ? "Refreshing…" : "Refresh"}
      </Button>
    </span>
  );
}
