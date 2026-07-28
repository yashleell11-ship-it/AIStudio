"use client";

import Link from "next/link";
import { useState } from "react";
import { Pin, PinOff } from "lucide-react";
import { ApiError } from "@/types/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { useReplaceSourcePins, useSourcePins, useSources } from "../hooks";
import { removeSourcePin, toggleSourcePin, unpinnedSources } from "../pins";
import type { SourcePin, SourceSummary } from "../types";
import { SourceLogo } from "./SourceLogo";

const TILE_CLASS =
  "group relative flex flex-col items-center gap-3 rounded-3xl border border-border bg-surface p-5 text-center transition duration-200";

function PinToggle({
  pinned,
  label,
  busy,
  onToggle,
}: {
  pinned: boolean;
  label: string;
  busy: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={(event) => {
        // The tile is a Link; keep the click on the button.
        event.preventDefault();
        event.stopPropagation();
        onToggle();
      }}
      disabled={busy}
      aria-pressed={pinned}
      aria-label={label}
      title={label}
      className={cn(
        "absolute right-2 top-2 z-10 flex size-8 items-center justify-center rounded-full bg-void/70 backdrop-blur-sm transition-opacity disabled:opacity-40",
        pinned
          ? "text-primary opacity-100"
          : "text-muted opacity-100 hover:text-fg sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100",
      )}
    >
      {pinned ? <PinOff className="size-4" aria-hidden /> : <Pin className="size-4" aria-hidden />}
    </button>
  );
}

function SourceTile({
  id,
  name,
  iconUrl,
  pinned,
  available,
  busy,
  onTogglePin,
}: {
  id: string;
  name: string;
  iconUrl: string | null;
  pinned: boolean;
  available: boolean;
  busy: boolean;
  onTogglePin: () => void;
}) {
  const body = (
    <>
      <SourceLogo
        id={id}
        name={name}
        iconUrl={iconUrl}
        size={72}
        className="bg-surface-2/80"
      />
      <p className="line-clamp-2 w-full font-display text-sm leading-snug text-fg">{name}</p>
    </>
  );
  const toggle = (
    <PinToggle
      pinned={pinned}
      label={pinned ? `Unpin ${name}` : `Pin ${name}`}
      busy={busy}
      onToggle={onTogglePin}
    />
  );

  // A pin whose connector no longer resolves (removed, renamed, or hidden by
  // the 18+ gate) is kept visible but not linkable, so it can be cleared
  // instead of quietly disappearing from an ordering the user arranged.
  if (!available) {
    return (
      <div className={cn(TILE_CLASS, "opacity-60")}>
        {body}
        <span className="text-[10px] uppercase tracking-wide text-muted">Unavailable</span>
        {toggle}
      </div>
    );
  }

  return (
    <Link href={`/sources/${id}`} className={cn(TILE_CLASS, "hover:scale-105 hover:border-primary/40")}>
      {body}
      {toggle}
    </Link>
  );
}

function SourceGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {children}
    </div>
  );
}

export function SourcesListView() {
  const sourcesQuery = useSources();
  const pinsQuery = useSourcePins();
  const replacePins = useReplaceSourcePins();
  const [pinError, setPinError] = useState<string | null>(null);

  if (sourcesQuery.isLoading) {
    return (
      <div className="page-shell">
        <div className="page-container">
          <div className="mb-8">
            <div className="h-10 w-32 animate-pulse rounded-lg bg-surface-2" />
          </div>
          <SourceGrid>
            {Array.from({ length: 12 }).map((_, index) => (
              <div
                key={index}
                className="flex flex-col items-center gap-3 rounded-3xl border border-border bg-surface p-5"
              >
                <div className="aspect-square w-full max-w-[72px] animate-pulse rounded-2xl bg-surface-2" />
                <div className="h-3 w-16 animate-pulse rounded bg-surface-2" />
              </div>
            ))}
          </SourceGrid>
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
  const pins = pinsQuery.data ?? [];
  const rest = unpinnedSources(sources, pins);
  // `PUT /sources/pins` replaces the WHOLE set, so a toggle computed before the
  // current set has been read would delete every pin this client has not seen.
  // No editing until the server's list is actually in hand.
  const pinsLoaded = pinsQuery.isSuccess;

  const applyPins = async (next: SourcePin[]) => {
    setPinError(null);
    try {
      await replacePins.mutateAsync(next);
    } catch (error) {
      setPinError(
        error instanceof ApiError ? error.message : "Failed to update your pinned sources.",
      );
    }
  };

  const togglePin = (source: SourceSummary) => applyPins(toggleSourcePin(pins, source));
  const unpin = (sourceId: string) => applyPins(removeSourcePin(pins, sourceId));

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8">
          <h1 className="page-title">Sources</h1>
        </div>

        {pinError ? (
          <div className="mb-6 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {pinError}
          </div>
        ) : null}

        {pinsQuery.isError ? (
          <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-border/50 bg-white/[0.02] px-4 py-3 text-sm text-muted">
            <span className="min-w-0 flex-1">
              Your pinned sources could not be loaded, so pinning is unavailable until
              they are.
            </span>
            <Button variant="secondary" size="sm" onClick={() => pinsQuery.refetch()}>
              Try again
            </Button>
          </div>
        ) : null}

        {sources.length === 0 ? (
          <div className="empty-state">
            <p className="text-lg font-medium text-fg">No sources installed</p>
          </div>
        ) : (
          <div className="space-y-10">
            {pins.length > 0 ? (
              <section>
                <div className="mb-3 flex items-center gap-2">
                  <Pin className="size-3.5 text-primary" aria-hidden />
                  <h2 className="text-[11px] font-semibold uppercase tracking-widest text-muted">
                    Pinned
                  </h2>
                </div>
                <SourceGrid>
                  {pins.map((pin) => (
                    <SourceTile
                      key={pin.source_id}
                      id={pin.source_id}
                      name={pin.name}
                      iconUrl={pin.icon_url}
                      pinned
                      available={pin.available}
                      busy={replacePins.isPending || !pinsLoaded}
                      onTogglePin={() => void unpin(pin.source_id)}
                    />
                  ))}
                </SourceGrid>
              </section>
            ) : null}

            <section>
              {pins.length > 0 ? (
                <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">
                  All sources
                </h2>
              ) : null}
              {rest.length === 0 ? (
                <p className="text-sm text-muted">Every installed source is pinned.</p>
              ) : (
                <SourceGrid>
                  {rest.map((source) => (
                    <SourceTile
                      key={source.id}
                      id={source.id}
                      name={source.name}
                      iconUrl={source.icon_url ?? null}
                      pinned={false}
                      available
                      busy={replacePins.isPending || !pinsLoaded}
                      onTogglePin={() => void togglePin(source)}
                    />
                  ))}
                </SourceGrid>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
