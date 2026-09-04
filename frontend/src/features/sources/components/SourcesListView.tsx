"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Pin, PinOff, Search, Telescope } from "lucide-react";
import { ApiError } from "@/types/api";
import { Button } from "@/components/ui/button";
import { useContentModeFilter } from "@/features/content-mode";
import { cn } from "@/lib/cn";
import { useReplaceSourcePins, useSourcePins, useSources } from "../hooks";
import { removeSourcePin, toggleSourcePin } from "../pins";
import { type SourcesFilter, sourceSections } from "../source-filter";
import type { SourcePin, SourceSummary } from "../types";
import { SourceLogo } from "./SourceLogo";

/**
 * The Sources screen: a searchable row list with a Pinned section.
 *
 * This replaced a logo grid. DESIGN_SYSTEM.md records why (2026-07-27): the
 * grid was designed when the catalogue was small, and at ~50 sources it gave no
 * way to find one and no room for a pin affordance. The mobile client was
 * rebuilt as a row list then; the web was not, so the two screens have been
 * different apps ever since. This is the web catching up — same search field,
 * same All/Pinned/18+ chips, same Pinned-above-All ordering, same 44px logo and
 * 44px pin target per row.
 */

/** 44px — the minimum comfortable touch target, and the mobile row's logo size. */
const LOGO_SIZE = 44;

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
        // The row is a Link; keep the click on the button.
        event.preventDefault();
        event.stopPropagation();
        onToggle();
      }}
      disabled={busy}
      aria-pressed={pinned}
      aria-label={label}
      title={label}
      className={cn(
        "flex size-11 shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-40",
        pinned ? "text-primary" : "text-muted hover:bg-fg/10 hover:text-fg",
      )}
    >
      {pinned ? <PinOff className="size-4" aria-hidden /> : <Pin className="size-4" aria-hidden />}
    </button>
  );
}

const ROW_CLASS =
  "flex items-center gap-3 rounded-2xl border border-border bg-surface px-3 py-2.5 transition-colors";

function SourceRowCard({
  source,
  pinned,
  unavailable,
  busy,
  onTogglePin,
}: {
  source: SourceSummary;
  pinned: boolean;
  unavailable: boolean;
  busy: boolean;
  onTogglePin: () => void;
}) {
  const body = (
    <>
      <SourceLogo
        id={source.id}
        name={source.name}
        iconUrl={source.icon_url ?? null}
        size={LOGO_SIZE}
        className="shrink-0 bg-surface-2/80"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          {/* Body face, not the display face — these are ~50 rows of proper
              nouns, and Syne at this size is decorative rather than legible. */}
          <p className="truncate text-sm font-medium text-fg">{source.name}</p>
          {source.mature ? (
            <span className="shrink-0 rounded-full bg-danger/15 px-1.5 py-px text-[0.625rem] font-bold tracking-wide text-danger">
              18+
            </span>
          ) : null}
        </div>
        {unavailable ? (
          <p className="mt-0.5 truncate text-xs text-muted">Unavailable</p>
        ) : source.description ? (
          <p className="mt-0.5 truncate text-xs text-muted">{source.description}</p>
        ) : null}
      </div>
    </>
  );

  const toggle = (
    <PinToggle
      pinned={pinned}
      label={pinned ? `Unpin ${source.name}` : `Pin ${source.name}`}
      busy={busy}
      onToggle={onTogglePin}
    />
  );

  // A pin whose connector no longer resolves stays visible but is not linkable,
  // so it can be cleared instead of quietly vanishing from the ordering.
  if (unavailable) {
    return (
      <div className={cn(ROW_CLASS, "opacity-60")}>
        {body}
        {toggle}
      </div>
    );
  }

  return (
    <div className={cn(ROW_CLASS, "hover:border-primary/40")}>
      <Link
        href={`/sources/${source.id}`}
        className="flex min-w-0 flex-1 items-center gap-3 outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {body}
      </Link>
      {toggle}
    </div>
  );
}

function SectionHeader({ icon: Icon, title }: { icon: typeof Pin; title: string }) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <Icon className="size-3.5 text-primary" aria-hidden />
      <h2 className="text-[11px] font-semibold uppercase tracking-widest text-muted">
        {title}
      </h2>
    </div>
  );
}

const CHIPS: Array<{ value: SourcesFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "pinned", label: "Pinned" },
  { value: "mature", label: "18+" },
];

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        // 30px tall on `py-1.5`, and "All" was only 44px WIDE — three small
        // pills side by side is the shape a thumb misses most reliably.
        "inline-flex items-center justify-center rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors",
        "[@media(pointer:coarse)]:min-h-11 [@media(pointer:coarse)]:min-w-11",
        active
          ? "border-primary/40 bg-primary/12 text-primary"
          : "border-border text-muted hover:text-fg",
      )}
    >
      {label}
    </button>
  );
}

export function SourcesListView() {
  const sourcesQuery = useSources();
  const pinsQuery = useSourcePins();
  const replacePins = useReplaceSourcePins();
  const [pinError, setPinError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<SourcesFilter>("all");

  // Scoped to the active content mode: a novel archive never appears beside
  // the manhwa sites, and vice versa. Straight off `content_kind`, so no
  // source-id index is needed here. A no-op when novels are disabled.
  const { filterSources, keepSource } = useContentModeFilter();
  const sources = useMemo(
    () => filterSources(sourcesQuery.data),
    [filterSources, sourcesQuery.data],
  );
  // Pins are one server-side set spanning both modes. `allPins` is what every
  // MUTATION works from — `PUT /sources/pins` replaces the whole set, so
  // toggling a pin computed from a mode-filtered list would silently delete
  // every pin belonging to the other mode. `pins` is the display slice only.
  const allPins = useMemo(() => pinsQuery.data ?? [], [pinsQuery.data]);
  const pins = useMemo(
    () => allPins.filter((pin) => keepSource(pin.source_id)),
    [allPins, keepSource],
  );
  const { pinned, rest } = useMemo(
    () => sourceSections({ sources, pins, query, filter }),
    [sources, pins, query, filter],
  );

  if (sourcesQuery.isLoading) {
    return (
      <div className="px-5 pb-8 pt-6 md:px-8">
        <div className="h-9 w-32 animate-pulse rounded-lg bg-surface-2" />
        <div className="mt-5 space-y-2">
          {Array.from({ length: 10 }).map((_, index) => (
            <div key={index} className={cn(ROW_CLASS, "gap-3")}>
              <div className="size-11 shrink-0 animate-pulse rounded-xl bg-surface-2" />
              <div className="flex-1 space-y-2">
                <div className="h-3.5 w-36 animate-pulse rounded bg-surface-2" />
                <div className="h-2.5 w-24 animate-pulse rounded bg-surface-2" />
              </div>
            </div>
          ))}
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

  // `PUT /sources/pins` replaces the WHOLE set, so a toggle computed before the
  // current set has been read would delete every pin this client has not seen.
  // No editing until the server's list is actually in hand.
  const pinsLoaded = pinsQuery.isSuccess;
  const busy = replacePins.isPending || !pinsLoaded;

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

  // Both edit the FULL set (see `allPins` above), never the display slice.
  const togglePin = (source: SourceSummary) => applyPins(toggleSourcePin(allPins, source));
  const unpin = (sourceId: string) => applyPins(removeSourcePin(allPins, sourceId));

  const nothingMatches = pinned.length === 0 && rest.length === 0;

  return (
    <div className="px-5 pb-8 pt-6 md:px-8">
      <h1 className="font-display text-3xl font-bold text-fg">Sources</h1>

      {/* With ~50 installed connectors the search field is the single
          highest-value control on this screen, so it leads. */}
      <div className="mt-4 space-y-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter sources…"
            aria-label="Filter sources"
            className="h-11 w-full rounded-full border border-border bg-surface pl-9 pr-4 text-sm text-fg outline-none placeholder:text-muted focus:border-primary/40 focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <div className="flex gap-2">
          {CHIPS.map((chip) => (
            <FilterChip
              key={chip.value}
              label={chip.label}
              active={filter === chip.value}
              onClick={() => setFilter(chip.value)}
            />
          ))}
        </div>
      </div>

      {pinError ? (
        <div className="mt-4 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {pinError}
        </div>
      ) : null}

      {pinsQuery.isError ? (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-border/50 bg-white/[0.02] px-4 py-3 text-sm text-muted">
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
        <p className="mt-10 text-center text-sm text-muted">No sources installed</p>
      ) : nothingMatches ? (
        <div className="mt-10 text-center">
          <p className="text-sm font-medium text-fg">
            {filter === "pinned" ? "No pinned sources" : "No sources match"}
          </p>
          <p className="mt-1 text-xs text-muted">
            {filter === "pinned"
              ? "Tap the pin on any source to keep it at the top."
              : "Try a different name."}
          </p>
        </div>
      ) : (
        <div className="mt-6 space-y-8">
          {pinned.length > 0 ? (
            <section>
              <SectionHeader icon={Pin} title="Pinned" />
              <div className="space-y-2">
                {pinned.map((row) => (
                  <SourceRowCard
                    key={row.source.id}
                    source={row.source}
                    pinned
                    unavailable={row.unavailable}
                    busy={busy}
                    onTogglePin={() => void unpin(row.source.id)}
                  />
                ))}
              </div>
            </section>
          ) : null}

          {rest.length > 0 ? (
            <section>
              <SectionHeader
                icon={Telescope}
                title={pinned.length > 0 ? "All sources" : "Sources"}
              />
              <div className="space-y-2">
                {rest.map((source) => (
                  <SourceRowCard
                    key={source.id}
                    source={source}
                    pinned={false}
                    unavailable={false}
                    busy={busy}
                    onTogglePin={() => void togglePin(source)}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
}
