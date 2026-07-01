"use client";

import Link from "next/link";
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  Minus,
  Plus,
  RotateCcw,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

const linkButtonClass =
  "inline-flex h-9 items-center justify-center gap-1 rounded-lg px-3 text-sm font-medium text-muted transition-colors hover:bg-white/10 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/40";

interface ReaderControlsProps {
  chapterTitle: string;
  scrollProgress: number;
  visiblePage: number;
  pageCount: number;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset: () => void;
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
  onBookmark,
  previousChapterHref,
  nextChapterHref,
  backHref,
  bookmarkPending,
  showBookmark = true,
  visible = true,
}: ReaderControlsProps) {
  return (
    <div
      className={cn(
        "pointer-events-none fixed inset-x-0 bottom-0 z-30 transition-all duration-300",
        visible ? "translate-y-0 opacity-100" : "translate-y-full opacity-0",
      )}
    >
      <div className="pointer-events-auto mx-auto max-w-3xl px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="glass-panel rounded-2xl p-4 shadow-glass">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-fg">{chapterTitle}</p>
              <p className="mt-0.5 font-mono text-xs tabular-nums text-muted">
                Page {visiblePage} / {pageCount} · {scrollProgress}%
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
            className="mb-4 h-1 bg-white/10 [&>div]:bg-gradient-to-r [&>div]:from-violet-500 [&>div]:to-cyan-500"
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
            </div>
          </div>
        </div>
      </div>
    </div>
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
        className="glass-card inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-fg transition-all hover:border-violet-500/30 hover:shadow-glow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/40"
      >
        {direction === "previous" ? (
          <ChevronLeft className="size-4 text-violet-400" />
        ) : null}
        {label}
        {direction === "next" ? (
          <ChevronRight className="size-4 text-violet-400" />
        ) : null}
      </Link>
    </div>
  );
}
