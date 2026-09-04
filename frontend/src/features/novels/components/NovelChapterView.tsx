"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ChevronRight, TriangleAlert, Type } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { OfflineState } from "@/components/ui/offline-state";
// The manga reader's own scroll writer, reused rather than re-derived: it
// rounds, clamps at zero and skips a no-op write.
import { setReaderScrollTop } from "@/features/reader/scroll-preparation";
import { useScrollContainer } from "@/lib/scroll-container";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";
import { isSceneBreak, splitDropCap, tocEntry } from "../book";
import { paletteSurface } from "../palettes";
import { activeParagraphIndex, paragraphForBucket, progressForParagraph } from "../progress";
import { formatChapterLength } from "../reading-time";
import { novelFontStack, stepFontSize } from "../typography";
import { useNovelPalette } from "../use-novel-palette";
import { useNovelPreferences } from "../use-novel-preferences";
import { useNovelShortcuts } from "../use-novel-shortcuts";
import type { NovelProgressPosition } from "../progress";
import type { NovelChapterContent } from "../types";
import { NovelTypePanel } from "./NovelTypePanel";

interface NovelChapterViewProps {
  chapter: NovelChapterContent | undefined;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  /** Identifies the series whose typography this reader restores. */
  preferencesKey: string;
  seriesTitle: string;
  /** The book's own page — where Escape and the back arrow go. */
  seriesHref: string;
  /** 1-based progress bucket to resume at. */
  initialBucket: number;
  previousChapterHref: string | null;
  nextChapterHref: string | null;
  /** Short label for the next chapter, e.g. "Chapter 41". */
  nextChapterLabel: string | null;
  /** Swap into the next chapter with no route navigation. */
  onSeamlessNext?: () => void;
  onProgress: (position: NovelProgressPosition) => void;
}

/** Where in the viewport a paragraph counts as "the one being read". */
const READING_LINE_RATIO = 0.35;
const SCROLL_EDGE_THRESHOLD = 48;
/** Wheel travel past the bottom that drops into the next chapter. */
const OVERSCROLL_TRIGGER = 140;
/** Breathing room above a resumed paragraph, so it is not flush to the head. */
const RESUME_OFFSET_PX = 96;

/**
 * A chapter of prose.
 *
 * The page is the whole design: a single column at the reader's own measure,
 * set in a system serif, on one of the twelve reading palettes. Everything else
 * — the running head, the progress hairline, the end-of-chapter block — is
 * furniture set in the muted ink, deliberately quiet enough to disappear while
 * reading and findable when looked for.
 *
 * Progress is reported in `progress.ts` buckets (paragraph position mapped onto
 * `last_page`/`page_count`), so the server's furthest-wins merge, "continue
 * reading" and the statistics service all keep working unchanged.
 *
 * Seamless continuation is the manga reader's mechanism, not a second one: at
 * the bottom an end card appears, and a tap or a continued downward scroll asks
 * the parent to swap the chapter in place — no route navigation, no flash. See
 * `features/reader/components/SourceReader.tsx`.
 */
export function NovelChapterView({
  chapter,
  isLoading,
  error,
  onRetry,
  preferencesKey,
  seriesTitle,
  seriesHref,
  initialBucket,
  previousChapterHref,
  nextChapterHref,
  nextChapterLabel,
  onSeamlessNext,
  onProgress,
}: NovelChapterViewProps) {
  const router = useRouter();
  const scrollElement = useScrollContainer();
  const { palette, choice, siteScheme, setChoice } = useNovelPalette();
  const {
    fontSize,
    lineHeight,
    measure,
    fontFamily,
    hydrated,
    update,
  } = useNovelPreferences(preferencesKey);

  const surface = useMemo(() => paletteSurface(palette), [palette]);
  const fontStack = novelFontStack(fontFamily);

  const [typePanelOpen, setTypePanelOpen] = useState(false);
  const [percent, setPercent] = useState(0);
  const [atBottom, setAtBottom] = useState(false);

  const paragraphs = useMemo(() => chapter?.paragraphs ?? [], [chapter]);
  const paragraphNodes = useRef<(HTMLParagraphElement | null)[]>([]);
  const offsetsRef = useRef<number[]>([]);
  const articleRef = useRef<HTMLElement>(null);
  const restoredRef = useRef(false);

  // Kept in refs so the scroll listener is attached once per chapter rather
  // than re-attached on every render that changes a callback's identity.
  const onProgressRef = useRef(onProgress);
  useEffect(() => {
    onProgressRef.current = onProgress;
  }, [onProgress]);
  const seamlessNextRef = useRef(onSeamlessNext);
  useEffect(() => {
    seamlessNextRef.current = onSeamlessNext;
  }, [onSeamlessNext]);

  /**
   * Each paragraph's distance from the top of the scroll container, measured
   * once per layout rather than per scroll: a long web-novel chapter runs to
   * hundreds of paragraphs, and reading a rect for every one of them on every
   * scroll frame would be the only expensive thing on the page. The ascending
   * array is then binary-searched by `activeParagraphIndex`.
   */
  const measureOffsets = useCallback(() => {
    const container = scrollElement;
    if (!container) return;
    const containerTop = container.getBoundingClientRect().top;
    const offsets: number[] = [];
    for (const node of paragraphNodes.current) {
      if (!node) continue;
      offsets.push(
        node.getBoundingClientRect().top - containerTop + container.scrollTop,
      );
    }
    offsetsRef.current = offsets;
  }, [scrollElement]);

  // Re-measured whenever anything that moves a paragraph changes: the chapter
  // itself, and every typography control.
  useLayoutEffect(() => {
    measureOffsets();
  }, [measureOffsets, paragraphs, fontSize, lineHeight, measure, fontFamily]);

  // …and when the column is re-flowed by something outside this component —
  // the window resizing, or the sidebar being collapsed.
  useEffect(() => {
    const node = articleRef.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measureOffsets());
    observer.observe(node);
    return () => observer.disconnect();
  }, [measureOffsets]);

  /**
   * Land on the saved paragraph, once, after the first real measurement.
   *
   * Held until `hydrated` because the stored type size decides where every
   * paragraph sits: restoring against default-size offsets and then applying a
   * 24px preference would drop the reader in the wrong place.
   */
  useEffect(() => {
    if (restoredRef.current || !hydrated || !scrollElement) return;
    if (paragraphs.length === 0) return;
    const offsets = offsetsRef.current;
    if (offsets.length === 0) return;
    restoredRef.current = true;
    if (initialBucket <= 1) return;
    const index = paragraphForBucket(initialBucket, paragraphs.length);
    const target = offsets[index];
    if (target == null) return;
    setReaderScrollTop(scrollElement, target - RESUME_OFFSET_PX);
  }, [hydrated, initialBucket, paragraphs.length, scrollElement]);

  const updateScrollState = useCallback(() => {
    const container = scrollElement;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    const maxScroll = Math.max(scrollHeight - clientHeight, 0);
    setPercent(maxScroll > 0 ? Math.round((scrollTop / maxScroll) * 100) : 100);
    setAtBottom(scrollTop + clientHeight >= scrollHeight - SCROLL_EDGE_THRESHOLD);

    const offsets = offsetsRef.current;
    if (offsets.length === 0) return;
    const index = activeParagraphIndex(
      offsets,
      scrollTop + clientHeight * READING_LINE_RATIO,
    );
    onProgressRef.current(progressForParagraph(index, offsets.length));
  }, [scrollElement]);

  useEffect(() => {
    const container = scrollElement;
    if (!container) return;
    let frame = 0;
    const handleScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(updateScrollState);
    };
    handleScroll();
    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      container.removeEventListener("scroll", handleScroll);
      cancelAnimationFrame(frame);
    };
  }, [scrollElement, updateScrollState]);

  // Continued scroll past the end card drops into the next chapter — the same
  // gesture, the same threshold, as the manga reader's continuous strip.
  useEffect(() => {
    if (!scrollElement || !atBottom || !onSeamlessNext) return;
    let overscroll = 0;
    let resetTimer: number | null = null;
    const handleWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey || event.deltaY <= 0) return;
      overscroll += event.deltaY;
      if (resetTimer) window.clearTimeout(resetTimer);
      resetTimer = window.setTimeout(() => {
        overscroll = 0;
      }, 320);
      if (overscroll >= OVERSCROLL_TRIGGER) {
        overscroll = 0;
        seamlessNextRef.current?.();
      }
    };
    scrollElement.addEventListener("wheel", handleWheel, { passive: true });
    return () => {
      scrollElement.removeEventListener("wheel", handleWheel);
      if (resetTimer) window.clearTimeout(resetTimer);
    };
  }, [scrollElement, atBottom, onSeamlessNext]);

  useNovelShortcuts({
    onPreviousChapter: () => {
      if (previousChapterHref) router.push(previousChapterHref);
    },
    onNextChapter: () => {
      if (onSeamlessNext) {
        onSeamlessNext();
      } else if (nextChapterHref) {
        router.push(nextChapterHref);
      }
    },
    onLargerText: () => update({ fontSize: stepFontSize(fontSize, 1) }),
    onSmallerText: () => update({ fontSize: stepFontSize(fontSize, -1) }),
    onToggleTypePanel: () => setTypePanelOpen((open) => !open),
    onEscape: () => {
      if (typePanelOpen) {
        setTypePanelOpen(false);
        return;
      }
      router.push(seriesHref);
    },
  });

  const viewState = resolveViewState({
    isLoading,
    error,
    isEmpty: chapter != null && paragraphs.length === 0,
  });

  const heading = useMemo(() => {
    if (!chapter) return { eyebrow: null as string | null, title: "Chapter" };
    const entry = tocEntry({ number: chapter.chapterNumber, title: chapter.title });
    const numbered = entry.ordinal ? `Chapter ${entry.ordinal}` : null;
    // When the source gave nothing but a number, that number IS the title —
    // printing it twice, once small and once large, is the tell of a template.
    return entry.title
      ? { eyebrow: numbered, title: entry.title }
      : { eyebrow: null, title: numbered ?? chapter.title };
  }, [chapter]);

  const lengthLine = chapter ? formatChapterLength(chapter.wordCount) : null;

  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: surface.bg, color: surface.ink }}
    >
      <RunningHead
        surface={surface}
        seriesTitle={seriesTitle}
        seriesHref={seriesHref}
        chapterLabel={heading.eyebrow ?? heading.title}
        percent={percent}
        typePanelOpen={typePanelOpen}
        onToggleTypePanel={() => setTypePanelOpen((open) => !open)}
        panel={
          typePanelOpen ? (
            <NovelTypePanel
              surface={surface}
              preferences={{ fontSize, lineHeight, measure, fontFamily }}
              onChange={update}
              choice={choice}
              onChoosePalette={setChoice}
              siteScheme={siteScheme}
              onClose={() => setTypePanelOpen(false)}
            />
          ) : null
        }
      />

      {viewState === "loading" || !hydrated ? (
        <ChapterSkeleton surface={surface} measure={measure} />
      ) : viewState === "offline" ? (
        <div className="mx-auto max-w-2xl px-6 py-16">
          <OfflineState
            reason="This chapter needs a connection to load."
            onRetry={onRetry}
          />
        </div>
      ) : viewState === "error" || !chapter ? (
        <div className="mx-auto max-w-2xl px-6 py-16">
          <EmptyState
            tone="error"
            icon={TriangleAlert}
            title="Couldn't load this chapter"
            description={apiErrorMessage(error, "The source did not answer.")}
            action={{ label: "Try again", onClick: onRetry }}
            secondaryAction={{ label: "Back to the book", href: seriesHref }}
          />
        </div>
      ) : viewState === "empty" ? (
        <div className="mx-auto max-w-2xl px-6 py-16">
          <EmptyState
            tone="error"
            icon={TriangleAlert}
            title="This chapter came through empty"
            description="The source answered, but with no text in it — usually a page that has been pulled or is still being published."
            action={{ label: "Try again", onClick: onRetry }}
            secondaryAction={{ label: "Back to the book", href: seriesHref }}
          />
        </div>
      ) : (
        <article
          ref={articleRef}
          className="mx-auto px-6 pb-24 pt-14 sm:pt-20"
          style={{
            maxWidth: `${measure}ch`,
            fontFamily: fontStack,
            fontSize: `${fontSize}px`,
            lineHeight: String(lineHeight),
          }}
        >
          <header className="mb-10">
            {heading.eyebrow ? (
              <p
                className="text-[0.6875em] font-semibold uppercase tracking-[0.22em]"
                style={{ color: surface.muted }}
              >
                {heading.eyebrow}
              </p>
            ) : null}
            <h1 className="mt-2 text-[1.55em] font-normal leading-[1.2]">
              {heading.title}
            </h1>
            <div
              className="mt-7 h-px w-14"
              style={{ backgroundColor: surface.rule }}
              aria-hidden
            />
          </header>

          <ChapterBody
            paragraphs={paragraphs}
            surface={surface}
            registerParagraph={(index, node) => {
              paragraphNodes.current[index] = node;
            }}
          />

          <footer className="mt-16">
            <div
              className="mx-auto h-px w-24"
              style={{ backgroundColor: surface.rule }}
              aria-hidden
            />
            <p
              className="mt-6 text-center text-[0.6875em] uppercase tracking-[0.22em]"
              style={{ color: surface.muted }}
            >
              End of {heading.eyebrow ?? heading.title}
            </p>
            {lengthLine ? (
              <p
                className="mt-2 text-center text-[0.75em]"
                style={{ color: surface.muted }}
              >
                {lengthLine}
              </p>
            ) : null}

            <div className="mt-10 flex flex-col items-center gap-3">
              {nextChapterHref && nextChapterLabel ? (
                <Link
                  href={nextChapterHref}
                  onClick={(event) => {
                    if (!onSeamlessNext) return;
                    if (
                      event.metaKey ||
                      event.ctrlKey ||
                      event.shiftKey ||
                      event.altKey
                    ) {
                      return;
                    }
                    event.preventDefault();
                    onSeamlessNext();
                  }}
                  className="group flex w-full max-w-sm items-center justify-between gap-4 rounded-xl px-5 py-4 transition-opacity hover:opacity-80"
                  style={{ border: `1px solid ${surface.rule}` }}
                >
                  <span className="min-w-0">
                    <span
                      className="block text-[0.625em] uppercase tracking-[0.22em]"
                      style={{ color: surface.muted }}
                    >
                      Next
                    </span>
                    <span className="mt-1 block truncate text-[0.95em]">
                      {nextChapterLabel}
                    </span>
                  </span>
                  <ChevronRight
                    className="size-5 shrink-0 transition-transform group-hover:translate-x-0.5"
                    aria-hidden
                  />
                </Link>
              ) : (
                <p className="text-[0.8125em]" style={{ color: surface.muted }}>
                  You have reached the last chapter this source has published.
                </p>
              )}

              <div
                className="flex items-center gap-4 text-[0.75em]"
                style={{ color: surface.muted }}
              >
                {previousChapterHref ? (
                  <Link href={previousChapterHref} className="hover:opacity-70">
                    Previous chapter
                  </Link>
                ) : null}
                <Link href={seriesHref} className="hover:opacity-70">
                  Back to the book
                </Link>
              </div>
            </div>
          </footer>
        </article>
      )}
    </div>
  );
}

/**
 * The running head: the book, the chapter, and how far in you are.
 *
 * Sticky rather than fixed, so it lives in the shell's own scroll container and
 * needs no knowledge of the reader's layout. Everything in it is set in the
 * muted ink — a running head that competes with the prose is a running head
 * nobody wants on the page.
 */
function RunningHead({
  surface,
  seriesTitle,
  seriesHref,
  chapterLabel,
  percent,
  typePanelOpen,
  onToggleTypePanel,
  panel,
}: {
  surface: ReturnType<typeof paletteSurface>;
  seriesTitle: string;
  seriesHref: string;
  chapterLabel: string;
  percent: number;
  typePanelOpen: boolean;
  onToggleTypePanel: () => void;
  panel: React.ReactNode;
}) {
  return (
    <div
      className="sticky top-0 z-40"
      style={{ backgroundColor: surface.bg, color: surface.ink }}
    >
      <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3 sm:px-6">
        <Link
          href={seriesHref}
          aria-label="Back to the book"
          className="flex size-8 shrink-0 items-center justify-center rounded-lg transition-opacity hover:opacity-70"
          style={{ color: surface.muted }}
        >
          <ArrowLeft className="size-4" aria-hidden />
        </Link>
        <p
          className="min-w-0 flex-1 truncate text-[0.6875rem] uppercase tracking-[0.18em]"
          style={{ color: surface.muted }}
        >
          <span className="truncate">{seriesTitle}</span>
          <span aria-hidden> · </span>
          <span className="truncate">{chapterLabel}</span>
        </p>
        <span
          className="shrink-0 text-[0.6875rem] tabular-nums"
          style={{ color: surface.muted }}
        >
          {percent}%
        </span>
        <div className="relative shrink-0">
          <button
            type="button"
            aria-label="Type and page settings"
            aria-expanded={typePanelOpen}
            onClick={onToggleTypePanel}
            className="flex size-8 items-center justify-center rounded-lg transition-opacity hover:opacity-70"
            style={{
              color: surface.ink,
              border: `1px solid ${typePanelOpen ? surface.rule : "transparent"}`,
            }}
          >
            <Type className="size-4" aria-hidden />
          </button>
          {panel}
        </div>
      </div>
      {/* The progress indicator: one hairline, the width of how far you are. */}
      <div className="h-px w-full" style={{ backgroundColor: surface.rule }}>
        <div
          className="h-px transition-[width] duration-150"
          style={{ width: `${percent}%`, backgroundColor: surface.muted }}
          aria-hidden
        />
      </div>
    </div>
  );
}

/**
 * The prose itself.
 *
 * Paragraphs are indented rather than spaced, which is how a book sets them and
 * is what makes a page of dialogue read as a page of a novel rather than as a
 * chat log. The opening paragraph is flush and carries the drop cap; scene
 * breaks are set centred with air around them instead of being run through the
 * body style as a line of asterisks.
 */
function ChapterBody({
  paragraphs,
  surface,
  registerParagraph,
}: {
  paragraphs: readonly string[];
  surface: ReturnType<typeof paletteSurface>;
  registerParagraph: (index: number, node: HTMLParagraphElement | null) => void;
}) {
  const dropCap = splitDropCap(paragraphs[0]);

  return (
    <>
      {paragraphs.map((paragraph, index) => {
        const register = (node: HTMLParagraphElement | null) =>
          registerParagraph(index, node);

        if (isSceneBreak(paragraph)) {
          return (
            <p
              key={index}
              ref={register}
              className="my-8 text-center tracking-[0.5em]"
              style={{ color: surface.muted }}
            >
              {paragraph.trim()}
            </p>
          );
        }

        if (index === 0 && dropCap) {
          return (
            <p key={index} ref={register} className="mt-0">
              <span
                className="float-left pr-[0.07em] font-normal"
                style={{ fontSize: "3.1em", lineHeight: 0.84, paddingTop: "0.04em" }}
              >
                {dropCap.initial}
              </span>
              {dropCap.rest}
            </p>
          );
        }

        return (
          <p
            key={index}
            ref={register}
            className={index === 0 ? "mt-0" : "mt-[0.35em] indent-[1.3em]"}
          >
            {paragraph}
          </p>
        );
      })}
    </>
  );
}

/**
 * The shape of a page of prose, while it loads.
 *
 * Lines at the reader's own measure rather than a generic block, so the column
 * does not jump width the moment the text arrives.
 */
function ChapterSkeleton({
  surface,
  measure,
}: {
  surface: ReturnType<typeof paletteSurface>;
  measure: number;
}) {
  const widths = [96, 99, 92, 97, 88, 98, 94, 99, 90, 96, 93, 87];
  return (
    <div
      className="mx-auto px-6 pb-24 pt-14 sm:pt-20"
      style={{ maxWidth: `${measure}ch` }}
      aria-busy="true"
      aria-label="Loading chapter"
    >
      <div
        className="h-3 w-24 rounded animate-pulse"
        style={{ backgroundColor: surface.rule }}
      />
      <div
        className="mt-4 h-7 w-2/3 rounded animate-pulse"
        style={{ backgroundColor: surface.rule }}
      />
      <div className="mt-12 space-y-4">
        {widths.map((width, index) => (
          <div
            key={index}
            className="h-3.5 rounded animate-pulse"
            style={{ width: `${width}%`, backgroundColor: surface.rule }}
          />
        ))}
      </div>
    </div>
  );
}
