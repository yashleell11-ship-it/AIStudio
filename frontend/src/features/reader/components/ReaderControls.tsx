"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  Minus,
  Plus,
  RotateCcw,
  Rows3,
  Settings2,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { usePrefersReducedMotion } from "@/components/premium/use-prefers-reduced-motion";

const linkButtonClass =
  "inline-flex h-9 items-center justify-center gap-1 rounded-lg px-3 text-sm font-medium text-muted transition-colors hover:bg-white/10 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40";

interface ReaderControlsProps {
  chapterTitle: string;
  scrollProgress: number;
  visiblePage: number;
  pageCount: number;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset: () => void;
  pageGap?: boolean;
  onTogglePageGap?: () => void;
  onBookmark?: () => void;
  previousChapterHref: string | null;
  nextChapterHref: string | null;
  backHref: string;
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
  pageGap = false,
  onTogglePageGap,
  onBookmark,
  previousChapterHref,
  nextChapterHref,
  backHref,
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
          <div className="rounded-t-3xl border border-border bg-surface-2 p-5 shadow-glass">
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
          </div>
        </div>
      </div>

      {/* Glass bottom bar — amber progress, chapter nav, and the settings gear. */}
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
              <Link
                href={backHref}
                className="shrink-0 rounded-lg px-3 py-1.5 text-xs text-muted transition-colors hover:bg-white/10 hover:text-fg"
              >
                Back
              </Link>
            </div>

            <Progress
              value={scrollProgress}
              className="mb-4 h-1.5 bg-white/10 [&>div]:shadow-[0_0_10px_rgba(245,158,11,0.45)]"
              aria-label="Chapter scroll progress"
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
