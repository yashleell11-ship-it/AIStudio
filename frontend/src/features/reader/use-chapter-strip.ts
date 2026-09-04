"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { chapterIndexOf, shouldExtendAhead, type StripChapter, type StripWindow } from "./strip";
import type { StripSource } from "./strip-source";
import { readerDebug } from "./debug";

export interface ChapterStripInput {
  /** The chapter the strip opens on — its first, and the anchor for its scroll. */
  entryChapterKey: string;
  /** The chapter being read right now; the window is kept around this one. */
  activeChapterKey: string;
  source: StripSource;
  window: StripWindow;
  /**
   * Hold the strip until whatever the source depends on is ready (Read-all
   * needs the series' chapter list before it can name a single key). The entry
   * chapter is not fetched while this is false.
   */
  ready?: boolean;
}

/** The chapter just outside one end of the strip, and what to call it. */
export interface StripEdge {
  chapterKey: string | null;
  label: string | null;
}

export interface ChapterStripState {
  /** Loaded chapters in reading order. Never has a hole in it. */
  chapters: readonly StripChapter[];
  /** The entry chapter has not arrived yet — there is nothing to render. */
  isLoading: boolean;
  /** The entry chapter failed. Anything later is a `nextError`, not this. */
  error: string | null;
  /** Why the chapter after the strip's tail did not arrive, if it did not. */
  nextError: string | null;
  /** What lies just before the strip's head, and just past its tail. */
  head: StripEdge;
  tail: StripEdge;
  retryNext: () => void;
  loadPrevious: () => void;
  loadingPrevious: boolean;
  /** Throw the strip away and rebuild it from the entry chapter. */
  reload: () => void;
}

/** Why the tail stopped growing, and whether time alone will fix it. */
interface TailFailure {
  error: string | null;
  retryAfterMs: number | null;
}

const NO_FAILURE: TailFailure = { error: null, retryAfterMs: null };

/** Identity of the strip currently loaded: which chapter, which attempt. */
interface StripIdentity {
  entryChapterKey: string;
  attempt: number;
}

function appendChapters(
  previous: readonly StripChapter[],
  loaded: readonly StripChapter[],
): StripChapter[] {
  const known = new Set(previous.map((chapter) => chapter.chapterKey));
  const next = [...previous];
  for (const chapter of loaded) {
    // A key already in the strip means two fetches raced; taking it twice would
    // put the same pages on screen twice, so the later one is simply dropped.
    if (known.has(chapter.chapterKey)) continue;
    known.add(chapter.chapterKey);
    next.push(chapter);
  }
  return next;
}

function prependChapters(
  previous: readonly StripChapter[],
  loaded: readonly StripChapter[],
): StripChapter[] {
  const known = new Set(previous.map((chapter) => chapter.chapterKey));
  const head = loaded.filter((chapter) => !known.has(chapter.chapterKey));
  return head.length === 0 ? [...previous] : [...head, ...previous];
}

/**
 * The loaded window of a continuous strip (spec 2026-09-05 R1/R2).
 *
 * One job: keep `window.ahead` chapters loaded past the one being read, so the
 * seam is crossed by scrolling and never by waiting. Chapters behind are kept
 * too — a boundary you can only cross one way is a trap — and the chapter
 * before the strip's own head is pulled only when asked for, since every
 * chapter opens at scroll zero and pulling it automatically would fetch a
 * chapter for every reader who never meant to go backwards.
 *
 * The strip only ever GROWS here. Bounding what is rendered is
 * `ContinuousStrip`'s business, and it does it by releasing pages to a spacer
 * of the same height rather than by dropping chapters — dropping one would move
 * everything below it under the reader.
 */
export function useChapterStrip({
  entryChapterKey,
  activeChapterKey,
  source,
  window: stripWindow,
  ready = true,
}: ChapterStripInput): ChapterStripState {
  const [chapters, setChapters] = useState<readonly StripChapter[]>([]);
  const [entryError, setEntryError] = useState<string | null>(null);
  const [next, setNext] = useState<TailFailure>(NO_FAILURE);
  const [loadingPrevious, setLoadingPrevious] = useState(false);
  const [identity, setIdentity] = useState<StripIdentity>({
    entryChapterKey,
    attempt: 0,
  });

  // Reset during render rather than in an effect: a new entry chapter is a new
  // strip, and rendering one frame of the old strip's pages under the new
  // chapter's chrome is exactly the flash this whole design exists to avoid.
  if (identity.entryChapterKey !== entryChapterKey) {
    setIdentity({ entryChapterKey, attempt: 0 });
    setChapters([]);
    setEntryError(null);
    setNext(NO_FAILURE);
    setLoadingPrevious(false);
  }

  /**
   * The source, held in a ref for the callbacks that must not re-run when it
   * changes identity: Read-all rebuilds its source every time the series'
   * chapter list is re-read, and that must not re-fetch the strip.
   */
  const sourceRef = useRef(source);
  const chaptersRef = useRef(chapters);
  const identityRef = useRef(identity);
  useEffect(() => {
    sourceRef.current = source;
    chaptersRef.current = chapters;
    identityRef.current = identity;
  }, [chapters, identity, source]);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    void sourceRef.current.fetch([identity.entryChapterKey]).then((result) => {
      if (cancelled) return;
      if (result.chapters.length === 0) {
        setEntryError(result.error ?? "That chapter did not load.");
        return;
      }
      setChapters(result.chapters);
    });
    return () => {
      cancelled = true;
    };
  }, [identity, ready]);

  /**
   * Keep the queue ahead of the reader full.
   *
   * Re-runs on every strip change, so a chapter arriving immediately triggers
   * the check for the one after it — which is what lets a window deeper than
   * one chapter fill itself without a scheduler.
   */
  const inFlightRef = useRef("");
  useEffect(() => {
    if (!ready || chapters.length === 0 || next.error) return;
    const activeIndex = Math.max(0, chapterIndexOf(chapters, activeChapterKey));
    if (!shouldExtendAhead(activeIndex, chapters.length, stripWindow.ahead)) return;

    const wanted = stripWindow.ahead - (chapters.length - 1 - activeIndex);
    const keys = sourceRef.current.keysAfter(chapters, wanted);
    if (keys.length === 0) return;

    // Two frames can want the same window (the reader crosses a seam while the
    // fetch that would have covered it is still out); one request answers both.
    const token = JSON.stringify(keys);
    if (inFlightRef.current === token) return;
    inFlightRef.current = token;

    let cancelled = false;
    readerDebug("strip-extend", { keys, activeChapterKey });
    void sourceRef.current
      .fetch(keys)
      .then((result) => {
        if (cancelled) return;
        if (result.chapters.length > 0) {
          setChapters((previous) => appendChapters(previous, result.chapters));
        }
        if (result.error) {
          setNext({ error: result.error, retryAfterMs: result.retryAfterMs ?? null });
        }
      })
      .finally(() => {
        if (inFlightRef.current === token) inFlightRef.current = "";
      });
    return () => {
      cancelled = true;
    };
  }, [activeChapterKey, chapters, identity, next.error, ready, stripWindow.ahead]);

  /**
   * Some failures pass on their own — the bulk window's rate limit above all —
   * and a reader fifty chapters into a run should not have to press anything to
   * get going again. Clearing the error re-arms the effect above.
   */
  useEffect(() => {
    if (next.retryAfterMs === null) return;
    const timer = setTimeout(() => setNext(NO_FAILURE), next.retryAfterMs);
    return () => clearTimeout(timer);
  }, [next]);

  const retryNext = useCallback(() => setNext(NO_FAILURE), []);
  const reload = useCallback(() => {
    setEntryError(null);
    setNext(NO_FAILURE);
    setIdentity((previous) => ({
      entryChapterKey: previous.entryChapterKey,
      attempt: previous.attempt + 1,
    }));
  }, []);

  const loadPrevious = useCallback(() => {
    if (loadingPrevious) return;
    const key = sourceRef.current.keyBefore(chaptersRef.current);
    if (!key) return;
    const identityAtRequest = identityRef.current;
    setLoadingPrevious(true);
    readerDebug("strip-prepend-requested", { key });
    void sourceRef.current
      .fetch([key])
      .then((result) => {
        // The strip this was asked for may have been replaced meanwhile; its
        // pages must not be pushed onto whatever took its place.
        if (identityRef.current !== identityAtRequest) return;
        if (result.chapters.length > 0) {
          setChapters((previous) => prependChapters(previous, result.chapters));
        }
      })
      .finally(() => setLoadingPrevious(false));
  }, [loadingPrevious]);

  const tailKey = chapters.length > 0 ? source.keysAfter(chapters, 1)[0] ?? null : null;
  const headKey = chapters.length > 0 ? source.keyBefore(chapters) : null;

  return {
    chapters,
    isLoading: chapters.length === 0 && entryError === null,
    error: entryError,
    nextError: next.error,
    head: { chapterKey: headKey, label: source.edgeLabel(chapters, "previous") },
    tail: { chapterKey: tailKey, label: source.edgeLabel(chapters, "next") },
    retryNext,
    loadPrevious,
    loadingPrevious,
    reload,
  };
}
