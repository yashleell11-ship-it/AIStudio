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
  Keyboard,
  Maximize,
  Minimize,
  Minus,
  MoveHorizontal,
  MoveVertical,
  Plus,
  RotateCcw,
  Rows3,
  ScrollText,
  Settings2,
  Square,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { formatKeyCombo } from "@/lib/keyboard";
import { Button } from "@/components/ui/button";
import { usePrefersReducedMotion } from "@/components/premium/use-prefers-reduced-motion";
import { SERIES_SHORTCUT_KEYS } from "../keymap";
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
