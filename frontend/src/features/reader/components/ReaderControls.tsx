"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeftRight,
  ArrowRightLeft,
  Bookmark,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Columns2,
  Film,
  Flame,
  Hand,
  Keyboard,
  Maximize,
  Minimize,
  Minus,
  MoveHorizontal,
  MoveVertical,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Rows3,
  ScrollText,
  Settings2,
  Sparkles,
  Square,
  SunDim,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { formatKeyCombo } from "@/lib/keyboard";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { usePrefersReducedMotion } from "@/components/premium/use-prefers-reduced-motion";
import { MAX_AUTO_SCROLL_SPEED, MIN_AUTO_SCROLL_SPEED } from "../auto-scroll";
import { AUTO_SCROLL_SHORTCUT_KEYS, SERIES_SHORTCUT_KEYS, type TapZone, type TapZoneConfig } from "../keymap";
import { MAX_DIMMER, MAX_WARMTH } from "../overlay";
import type { FitMode, ReadingDirection, ReadingMode } from "../types";
import { ScrubBar } from "./ScrubBar";

const linkButtonClass =
  "inline-flex h-9 items-center justify-center gap-1 rounded-lg px-3 text-sm font-medium text-muted transition-colors hover:bg-white/10 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40";

interface SegmentOption<T extends string> {
  value: T;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
  title?: string;
}

/**
 * Warm segmented picker used by the mode / fit / direction rows. Kept local to
 * the reader: it is a settings-sheet affordance, not a shared primitive.
 */
function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: SegmentOption<T>[];
  onChange: (next: T) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-sm font-medium text-fg">{label}</span>
      <div
        role="group"
        aria-label={label}
        className="flex items-center gap-1 rounded-xl border border-border/60 bg-white/[0.03] p-1"
      >
        {options.map((option) => {
          const Icon = option.icon;
          const active = option.value === value;
          return (
            <Button
              key={option.value}
              variant="ghost"
              size="sm"
              disabled={option.disabled}
              title={option.title}
              aria-pressed={active}
              onClick={() => onChange(option.value)}
              className={cn(
                "gap-1.5 px-2.5 transition-colors hover:bg-white/10",
                active
                  ? "bg-primary/15 text-primary hover:text-primary"
                  : "text-muted hover:text-fg",
              )}
            >
              <Icon className="size-4" />
              <span className="hidden sm:inline">{option.label}</span>
            </Button>
          );
        })}
      </div>
    </div>
  );
}

/** One physical zone's action picker in the "Tap zones" settings row. */
const TAP_ZONE_OPTIONS: SegmentOption<TapZone>[] = [
  { value: "retreat", label: "Previous", icon: ChevronLeft },
  { value: "toggle", label: "Toggle", icon: Hand },
  { value: "advance", label: "Next", icon: ChevronRight },
];

function TapZoneRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: TapZone;
  onChange: (action: TapZone) => void;
}) {
  return (
    <Segmented<TapZone>
      label={label}
      value={value}
      onChange={onChange}
      options={TAP_ZONE_OPTIONS}
    />
  );
}

interface ReaderControlsProps {
  chapterTitle: string;
  scrollProgress: number;
  visiblePage: number;
  pageCount: number;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset: () => void;
  readingMode: ReadingMode;
  onReadingModeChange: (mode: ReadingMode) => void;
  fitMode: FitMode;
  onFitModeChange: (mode: FitMode) => void;
  direction: ReadingDirection;
  onDirectionChange: (direction: ReadingDirection) => void;
  onSeekPage: (page: number) => void;
  fullscreen: boolean;
  fullscreenSupported: boolean;
  onToggleFullscreen: () => void;
  onShowShortcuts: () => void;
  pageGap?: boolean;
  onTogglePageGap?: () => void;
  cinema?: boolean;
  onToggleCinema?: () => void;
  /** Subtle fade between page turns. Paged mode only. */
  pageTransition?: boolean;
  onTogglePageTransition?: () => void;
  /** Auto-scroll only ever drives the continuous strip. */
  autoScrollAvailable?: boolean;
  autoScrollPlaying?: boolean;
  onToggleAutoScroll?: () => void;
  /** 1 (slowest) to 10 (fastest) — see `auto-scroll.ts`. */
  autoScrollSpeed?: number;
  onAutoScrollSpeedChange?: (speed: number) => void;
  autoScrollReducedMotion?: boolean;
  /** Night-reading dimmer, 0..`MAX_DIMMER`. */
  dimmer?: number;
  onDimmerChange?: (value: number) => void;
  /** Night-reading warmth tint, 0..`MAX_WARMTH`. */
  warmth?: number;
  onWarmthChange?: (value: number) => void;
  /** Resolved (never null) left/centre/right tap behaviour, so the settings
   * sheet can show what's actually in effect right now. */
  tapZones?: TapZoneConfig;
  onTapZonesChange?: (config: TapZoneConfig) => void;
  onBookmark?: () => void;
  previousChapterHref: string | null;
  nextChapterHref: string | null;
  /** This chapter's series page — a real href, so it opens in a new tab too. */
  seriesHref: string;
  /** Plain-click / shortcut route to `seriesHref`, which also drops fullscreen. */
  onOpenSeries: () => void;
  bookmarkPending?: boolean;
  showBookmark?: boolean;
  visible?: boolean;
}

export function ReaderControls({
  chapterTitle,
  scrollProgress,
  visiblePage,
  pageCount,
  zoom,
  onZoomIn,
  onZoomOut,
  onZoomReset,
  readingMode,
  onReadingModeChange,
  fitMode,
  onFitModeChange,
  direction,
  onDirectionChange,
  onSeekPage,
  fullscreen,
  fullscreenSupported,
  onToggleFullscreen,
  onShowShortcuts,
  pageGap = false,
  onTogglePageGap,
  cinema = false,
  onToggleCinema,
  pageTransition = false,
  onTogglePageTransition,
  autoScrollAvailable = false,
  autoScrollPlaying = false,
  onToggleAutoScroll,
  autoScrollSpeed,
  onAutoScrollSpeedChange,
  autoScrollReducedMotion = false,
  dimmer = 0,
  onDimmerChange,
  warmth = 0,
  onWarmthChange,
  tapZones,
  onTapZonesChange,
  onBookmark,
  previousChapterHref,
  nextChapterHref,
  seriesHref,
  onOpenSeries,
  bookmarkPending,
  showBookmark = true,
  visible = true,
}: ReaderControlsProps) {
  const reduceMotion = usePrefersReducedMotion();
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Keep the settings sheet in sync with the chrome: hiding the controls (tap to
  // toggle) must also dismiss the sheet so it never lingers over a clean page.
  // Done as a render-time adjustment (not an effect) so it resets on the same
  // commit the chrome hides — avoiding the cascading-render effect lint.
  const [prevVisible, setPrevVisible] = useState(visible);
  if (prevVisible !== visible) {
    setPrevVisible(visible);
    if (!visible && settingsOpen) {
      setSettingsOpen(false);
    }
  }

  const continuous = readingMode === "continuous";

  return (
    <>
      {/* Settings backdrop — warm scrim, taps close the sheet. */}
      <div
        className={cn(
          "fixed inset-0 z-30 bg-black/40",
          reduceMotion ? "" : "transition-opacity duration-300",
          settingsOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={() => setSettingsOpen(false)}
        aria-hidden
      />

      {/* Settings sheet — elevated rounded-top surface with warm/amber toggles. */}
      <div
        className={cn(
          "pointer-events-none fixed inset-x-0 bottom-0 z-40",
          reduceMotion ? "" : "transition-transform duration-300 ease-out",
          settingsOpen ? "translate-y-0" : "translate-y-full",
        )}
        role="dialog"
        aria-label="Reader settings"
        aria-hidden={!settingsOpen}
      >
        <div className="pointer-events-auto mx-auto max-w-3xl px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <div className="max-h-[75vh] overflow-y-auto rounded-t-3xl border border-border bg-surface-2 p-5 shadow-glass">
            <div className="mb-4 flex items-center justify-between">
              <p className="font-display text-base tracking-wide text-fg">Reader settings</p>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSettingsOpen(false)}
                aria-label="Close settings"
                className="size-8 text-muted hover:bg-white/10 hover:text-fg"
              >
                <X className="size-4" />
              </Button>
            </div>

            <Segmented<ReadingMode>
              label="Layout"
              value={readingMode}
              onChange={onReadingModeChange}
              options={[
                { value: "single", label: "Single", icon: Square },
                { value: "double", label: "Double", icon: Columns2 },
                { value: "continuous", label: "Strip", icon: ScrollText },
              ]}
            />

            <Segmented<ReadingDirection>
              label="Direction"
              value={direction}
              onChange={onDirectionChange}
              options={[
                {
                  value: "ltr",
                  label: "LTR",
                  icon: ArrowLeftRight,
                  title: "Left to right — webtoons and western comics",
                },
                {
                  value: "rtl",
                  label: "RTL",
                  icon: ArrowRightLeft,
                  title: "Right to left — manga",
                },
              ]}
            />

            <Segmented<FitMode>
              label="Fit"
              value={fitMode}
              onChange={onFitModeChange}
              options={[
                { value: "width", label: "Width", icon: MoveHorizontal },
                {
                  value: "height",
                  label: "Height",
                  icon: MoveVertical,
                  disabled: continuous,
                  title: continuous
                    ? "A continuous strip has no single page height to fit"
                    : undefined,
                },
                {
                  value: "original",
                  label: "Original",
                  icon: Maximize,
                  disabled: continuous,
                  title: continuous
                    ? "Continuous scrolling always fits the reading column"
                    : undefined,
                },
              ]}
            />

            <div className="flex items-center justify-between gap-3 py-2">
              <span className="text-sm font-medium text-fg">Zoom</span>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onZoomOut}
                  aria-label="Zoom out"
                  className="size-9 text-muted hover:bg-white/10 hover:text-fg"
                >
                  <Minus className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onZoomReset}
                  aria-label="Reset zoom"
                  className="min-w-[3.5rem] font-mono text-xs tabular-nums text-muted hover:bg-white/10 hover:text-fg"
                >
                  <RotateCcw className="mr-1 size-3" />
                  {Math.round(zoom * 100)}%
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onZoomIn}
                  aria-label="Zoom in"
                  className="size-9 text-muted hover:bg-white/10 hover:text-fg"
                >
                  <Plus className="size-4" />
                </Button>
              </div>
            </div>
            <p className="-mt-1 mb-1 text-xs text-muted">
              Hold Ctrl (or ⌘) while scrolling to zoom; scrolling on its own always scrolls.
            </p>

            {onTogglePageGap ? (
              <div className="flex items-center justify-between gap-3 py-2">
                <span className="text-sm font-medium text-fg">Page gap</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onTogglePageGap}
                  aria-label="Toggle page gap"
                  aria-pressed={pageGap}
                  className={cn(
                    "gap-2 transition-colors hover:bg-white/10",
                    pageGap
                      ? "bg-primary/15 text-primary hover:text-primary"
                      : "text-muted hover:text-fg",
                  )}
                >
                  <Rows3 className="size-4" />
                  {pageGap ? "On" : "Off"}
                </Button>
              </div>
            ) : null}

            {onToggleCinema ? (
              <div className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-fg">Cinema mode</span>
                  <span className="mt-0.5 block text-xs text-muted">
                    Hides all controls after a few idle seconds. Press C, or tap to
                    bring them back.
                  </span>
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onToggleCinema}
                  aria-label="Toggle cinema mode"
                  aria-pressed={cinema}
                  className={cn(
                    "shrink-0 gap-2 transition-colors hover:bg-white/10",
                    cinema
                      ? "bg-primary/15 text-primary hover:text-primary"
                      : "text-muted hover:text-fg",
                  )}
                >
                  <Film className="size-4" />
                  {cinema ? "On" : "Off"}
                </Button>
              </div>
            ) : null}

            {onTogglePageTransition ? (
              <div className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-fg">Page transition</span>
                  <span className="mt-0.5 block text-xs text-muted">
                    A subtle fade between page turns.
                  </span>
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onTogglePageTransition}
                  aria-label="Toggle page transition"
                  aria-pressed={pageTransition}
                  className={cn(
                    "shrink-0 gap-2 transition-colors hover:bg-white/10",
                    pageTransition
                      ? "bg-primary/15 text-primary hover:text-primary"
                      : "text-muted hover:text-fg",
                  )}
                >
                  <Sparkles className="size-4" />
                  {pageTransition ? "On" : "Off"}
                </Button>
              </div>
            ) : null}

            {autoScrollAvailable && onToggleAutoScroll ? (
              <div className="border-t border-border/60 py-2 pt-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-fg">Auto-scroll</span>
                    <span className="mt-0.5 block text-xs text-muted">
                      Scrolls the strip for you at the speed below. Press P, tap
                      anywhere, or scroll manually to pause.
                    </span>
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onToggleAutoScroll}
                    aria-label={autoScrollPlaying ? "Pause auto-scroll" : "Play auto-scroll"}
                    aria-pressed={autoScrollPlaying}
                    title={`${autoScrollPlaying ? "Pause" : "Play"} (${formatKeyCombo(AUTO_SCROLL_SHORTCUT_KEYS).join(" ")})`}
                    className={cn(
                      "shrink-0 gap-2 transition-colors hover:bg-white/10",
                      autoScrollPlaying
                        ? "bg-primary/15 text-primary hover:text-primary"
                        : "text-muted hover:text-fg",
                    )}
                  >
                    {autoScrollPlaying ? (
                      <Pause className="size-4" />
                    ) : (
                      <Play className="size-4" />
                    )}
                    {autoScrollPlaying ? "Pause" : "Play"}
                  </Button>
                </div>
                {onAutoScrollSpeedChange && autoScrollSpeed != null ? (
                  <label className="mt-2 flex items-center gap-3">
                    <span className="w-14 shrink-0 text-xs text-muted">Speed</span>
                    <Slider
                      value={autoScrollSpeed}
                      min={MIN_AUTO_SCROLL_SPEED}
                      max={MAX_AUTO_SCROLL_SPEED}
                      step={1}
                      onChange={onAutoScrollSpeedChange}
                      aria-label="Auto-scroll speed"
                    />
                    <span className="w-6 shrink-0 text-right font-mono text-xs tabular-nums text-muted">
                      {autoScrollSpeed}
                    </span>
                  </label>
                ) : null}
                {autoScrollReducedMotion ? (
                  <p className="mt-1.5 text-xs text-muted">
                    Reduced motion is on, so this never starts on its own — Play
                    still works whenever you want it.
                  </p>
                ) : null}
              </div>
            ) : null}

            {onDimmerChange ? (
              <label className="flex items-center gap-3 border-t border-border/60 py-2 pt-3">
                <SunDim className="size-4 shrink-0 text-muted" aria-hidden />
                <span className="w-16 shrink-0 text-sm font-medium text-fg">Brightness</span>
                <Slider
                  value={dimmer}
                  min={0}
                  max={MAX_DIMMER}
                  step={0.01}
                  onChange={onDimmerChange}
                  aria-label="Dim the page"
                />
                <span className="w-9 shrink-0 text-right font-mono text-xs tabular-nums text-muted">
                  {Math.round((1 - dimmer / MAX_DIMMER) * 100)}%
                </span>
              </label>
            ) : null}

            {onWarmthChange ? (
              <label className="flex items-center gap-3 py-2">
                <Flame className="size-4 shrink-0 text-muted" aria-hidden />
                <span className="w-16 shrink-0 text-sm font-medium text-fg">Warmth</span>
                <Slider
                  value={warmth}
                  min={0}
                  max={MAX_WARMTH}
                  step={0.01}
                  onChange={onWarmthChange}
                  aria-label="Warm the page"
                />
                <span className="w-9 shrink-0 text-right font-mono text-xs tabular-nums text-muted">
                  {Math.round((warmth / MAX_WARMTH) * 100)}%
                </span>
              </label>
            ) : null}

            {tapZones && onTapZonesChange ? (
              <div className="border-t border-border/60 py-2 pt-3">
                <div className="mb-1 flex items-center gap-2">
                  <Hand className="size-4 text-muted" aria-hidden />
                  <span className="text-sm font-medium text-fg">Tap zones</span>
                </div>
                <p className="mb-1.5 text-xs text-muted">
                  What each side of the page does when tapped. Mirrors automatically
                  for a right-to-left series until you set your own.
                </p>
                <TapZoneRow
                  label="Left"
                  value={tapZones.left}
                  onChange={(action) => onTapZonesChange({ ...tapZones, left: action })}
                />
                <TapZoneRow
                  label="Center"
                  value={tapZones.center}
                  onChange={(action) => onTapZonesChange({ ...tapZones, center: action })}
                />
                <TapZoneRow
                  label="Right"
                  value={tapZones.right}
                  onChange={(action) => onTapZonesChange({ ...tapZones, right: action })}
                />
              </div>
            ) : null}

            <div className="mt-2 flex items-center justify-between gap-3 border-t border-border/60 pt-3">
              {fullscreenSupported ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onToggleFullscreen}
                  aria-pressed={fullscreen}
                  className="gap-2 text-muted hover:bg-white/10 hover:text-fg"
                >
                  {fullscreen ? (
                    <Minimize className="size-4" />
                  ) : (
                    <Maximize className="size-4" />
                  )}
                  {fullscreen ? "Exit fullscreen" : "Fullscreen"}
                </Button>
              ) : (
                <span />
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={onShowShortcuts}
                className="gap-2 text-muted hover:bg-white/10 hover:text-fg"
              >
                <Keyboard className="size-4" />
                Shortcuts
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Glass bottom bar — amber scrubber, chapter nav, and the settings gear. */}
      <div
        className={cn(
          "pointer-events-none fixed inset-x-0 bottom-0 z-30",
          reduceMotion ? "" : "transition-all duration-300",
          visible ? "translate-y-0 opacity-100" : "translate-y-full opacity-0",
        )}
      >
        <div className="pointer-events-auto mx-auto max-w-3xl px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <div className="glass-panel rounded-2xl p-4 shadow-glass">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-fg">{chapterTitle}</p>
                <p className="mt-0.5 font-mono text-xs tabular-nums text-primary">
                  Page {visiblePage} / {pageCount}
                  <span className="text-muted"> · {scrollProgress}%</span>
                </p>
              </div>
              {/*
                Out of the chapter and into its own series page. A real Link so
                middle-click and "open in new tab" behave, but a plain click is
                handled by the reader, which leaves fullscreen on the way out.
              */}
              <Link
                href={seriesHref}
                // Hint rendered from the binding itself, so the tooltip cannot
                // drift from the key the registry actually listens for.
                title={`Go to series page (${formatKeyCombo(SERIES_SHORTCUT_KEYS).join(" ")})`}
                onClick={(event) => {
                  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                    return;
                  }
                  event.preventDefault();
                  onOpenSeries();
                }}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-muted transition-colors hover:bg-white/10 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
              >
                <BookOpen className="size-4 text-primary" />
                Series
              </Link>
            </div>

            <ScrubBar
              className="mb-4"
              page={visiblePage}
              pageCount={pageCount}
              direction={direction}
              onSeek={onSeekPage}
            />

            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1">
                {previousChapterHref != null ? (
                  <Link href={previousChapterHref} className={cn(linkButtonClass)}>
                    <ChevronLeft className="size-4" />
                    Prev
                  </Link>
                ) : (
                  <span className={cn(linkButtonClass, "pointer-events-none opacity-30")}>
                    <ChevronLeft className="size-4" />
                    Prev
                  </span>
                )}
                {nextChapterHref != null ? (
                  <Link href={nextChapterHref} className={cn(linkButtonClass)}>
                    Next
                    <ChevronRight className="size-4" />
                  </Link>
                ) : (
                  <span className={cn(linkButtonClass, "pointer-events-none opacity-30")}>
                    Next
                    <ChevronRight className="size-4" />
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1">
                {showBookmark && onBookmark ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onBookmark}
                    disabled={bookmarkPending}
                    aria-label={`Bookmark page ${visiblePage}`}
                    className="text-muted hover:bg-white/10 hover:text-fg"
                  >
                    <Bookmark className="size-4" />
                    Save
                  </Button>
                ) : null}
                {autoScrollAvailable && onToggleAutoScroll ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={onToggleAutoScroll}
                    aria-label={autoScrollPlaying ? "Pause auto-scroll" : "Play auto-scroll"}
                    aria-pressed={autoScrollPlaying}
                    title={`${autoScrollPlaying ? "Pause" : "Play"} auto-scroll (${formatKeyCombo(AUTO_SCROLL_SHORTCUT_KEYS).join(" ")})`}
                    className={cn(
                      "size-9 hover:bg-white/10 hover:text-fg",
                      autoScrollPlaying ? "bg-primary/15 text-primary" : "text-muted",
                    )}
                  >
                    {autoScrollPlaying ? (
                      <Pause className="size-4" />
                    ) : (
                      <Play className="size-4" />
                    )}
                  </Button>
                ) : null}
                {fullscreenSupported ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={onToggleFullscreen}
                    aria-label={fullscreen ? "Exit fullscreen" : "Enter fullscreen"}
                    aria-pressed={fullscreen}
                    className={cn(
                      "size-9 hover:bg-white/10 hover:text-fg",
                      fullscreen ? "bg-primary/15 text-primary" : "text-muted",
                    )}
                  >
                    {fullscreen ? (
                      <Minimize className="size-4" />
                    ) : (
                      <Maximize className="size-4" />
                    )}
                  </Button>
                ) : null}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setSettingsOpen((open) => !open)}
                  aria-label="Reader settings"
                  aria-pressed={settingsOpen}
                  className={cn(
                    "size-9 hover:bg-white/10 hover:text-fg",
                    settingsOpen ? "bg-primary/15 text-primary" : "text-muted",
                  )}
                >
                  <Settings2 className="size-4" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

interface ChapterEdgePromptProps {
  href: string;
  direction: "previous" | "next";
  label: string;
}

export function ChapterEdgePrompt({ href, direction, label }: ChapterEdgePromptProps) {
  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-3xl justify-center px-4 py-6",
        direction === "previous" ? "pb-2" : "pt-2",
      )}
    >
      <Link
        href={href}
        onClick={(event) => event.stopPropagation()}
        className="glass-card inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-fg transition-all hover:border-primary/30 hover:shadow-glow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        {direction === "previous" ? (
          <ChevronLeft className="size-4 text-primary" />
        ) : null}
        {label}
        {direction === "next" ? (
          <ChevronRight className="size-4 text-primary" />
        ) : null}
      </Link>
    </div>
  );
}

interface ChapterEndCardProps {
  /** Real href for the next chapter (middle-click / open-in-new-tab). */
  href: string;
  /** Short label, e.g. "Ch 41". */
  label: string;
  /** Swap into the next chapter with no route navigation. */
  onAdvance: () => void;
}

/**
 * End-of-chapter affordance for the continuous strip (spec §3.3.4). Slides up
 * as the reader reaches the bottom (the CSS animation collapses to an instant
 * appearance under reduced motion); a tap — or a continued downward scroll,
 * handled by `ChapterReader` — swaps straight into the next chapter, which is
 * already prefetched, with no full-page navigation.
 */
export function ChapterEndCard({ href, label, onAdvance }: ChapterEndCardProps) {
  return (
    <div className="mx-auto flex w-full max-w-3xl justify-center overflow-hidden px-4 pb-10 pt-4">
      <Link
        href={href}
        onClick={(event) => {
          event.stopPropagation();
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          onAdvance();
        }}
        className="glass-card group reader-end-card-enter flex w-full max-w-md flex-col items-center gap-1 rounded-2xl px-6 py-5 text-center shadow-glass focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <span className="text-[11px] font-semibold uppercase tracking-widest text-muted">
          Next chapter
        </span>
        <span className="flex items-center gap-1.5 text-base font-semibold text-fg">
          {label}
          <ChevronRight className="size-4 text-primary transition-transform group-hover:translate-x-0.5" />
        </span>
        <span className="mt-0.5 text-xs text-muted">Tap or keep scrolling</span>
      </Link>
    </div>
  );
}
