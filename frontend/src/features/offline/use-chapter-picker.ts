"use client";

import { useCallback, useMemo, useState } from "react";
import { isFullySaved } from "./format";
import {
  EMPTY_CHAPTER_SELECTION,
  addChapters,
  everyChapter,
  extendChapterSelection,
  nextChapters,
  toggleChapter,
  unreadChapters,
  type ChapterSelection,
  type SelectableChapter,
} from "./chapter-selection";
import { planDownload } from "./download-queue";
import type { SaveChapterRequest } from "./protocol";
import { useSeriesDownloads, type SeriesDownloads } from "./use-series-downloads";
import { retainSelection } from "@/features/library/selection";
import type { ChapterDownloadState } from "./series-downloads";

/**
 * Everything a series page needs to offer downloads: what is already on the
 * device, what is ticked, and the one action that stores it all.
 *
 * One hook rather than three so the manga page, the book page and the library's
 * own series page wire up identically — the three lists differ in how a row
 * looks and in how a chapter's bytes are found, and in nothing else.
 */

/** The owner's "download 10 chapters in 1 go", as a button. */
export const NEXT_BATCH_SIZE = 10;

export interface ChapterPickerRow {
  key: string;
  number: number | null;
  /** Finished, per the reading progress the page already has. */
  read: boolean;
}

export interface ChapterPicker {
  downloads: SeriesDownloads;
  /** Selection mode is on: rows tick instead of opening. */
  selecting: boolean;
  begin: () => void;
  end: () => void;
  selection: ChapterSelection;
  selectedCount: number;
  isSelected: (chapterKey: string) => boolean;
  /** A row click while selecting. `shift` extends from the last plain click. */
  pick: (chapterKey: string, shift: boolean) => void;
  /** Chapters the current selection would actually download. */
  plan: string[];
  /** Every listed chapter not already on the device, in reading order. */
  unsaved: string[];
  /** The range helpers, each already filtered to what is not on the device. */
  helpers: { id: string; label: string; keys: string[] }[];
  applyHelper: (keys: readonly string[]) => void;
  stateOf: (chapterKey: string) => ChapterDownloadState;
  /** Download the current selection. */
  start: () => void;
  /** Download an explicit set — the book page's "Download book". */
  startKeys: (keys: readonly string[]) => void;
  /** How many of the listed chapters are fully on the device. */
  savedCount: number;
  total: number;
}

export interface ChapterPickerInput {
  sourceId: string;
  seriesKey: string;
  /**
   * The chapters AS DISPLAYED, in the order the rows are rendered.
   *
   * Shift-click ranges over what is on screen — a reader dragging from the
   * fourth row to the ninth means those six rows, whatever order the source
   * listed them in — so a page that sorts newest-first must hand them over
   * newest-first. Everything else (the range helpers, and the order a run
   * actually downloads in) re-sorts into reading order for itself.
   */
  chapters: readonly ChapterPickerRow[];
  buildRequest: (chapterKey: string) => Promise<SaveChapterRequest | null>;
  /**
   * Warm a window of what is coming, in one round trip. See
   * `DownloadQueueDeps.prepare` — without it a ten-chapter run is ten single
   * fetches on the rate limiter's `sources` bucket.
   */
  prepare?: (upcoming: readonly string[]) => Promise<void>;
  /**
   * Prose gets a whole-series helper; page images do not. A 400-chapter book is
   * a few megabytes of text, and the same count of manga is gigabytes — the
   * difference the owner's "download whole series for novels too" turns on.
   */
  medium: "manga" | "novel";
}

export function useChapterPicker({
  sourceId,
  seriesKey,
  chapters,
  buildRequest,
  prepare,
  medium,
}: ChapterPickerInput): ChapterPicker {
  const downloads = useSeriesDownloads({ sourceId, seriesKey, buildRequest, prepare });
  const [selecting, setSelecting] = useState(false);
  const [selection, setSelection] = useState<ChapterSelection>(EMPTY_CHAPTER_SELECTION);

  const rows = useMemo<SelectableChapter[]>(
    () =>
      chapters.map((chapter) => ({
        key: chapter.key,
        number: chapter.number,
        read: chapter.read,
        saved: isFullySaved(downloads.saved.get(chapter.key)),
      })),
    [chapters, downloads.saved],
  );

  const keys = useMemo(() => rows.map((row) => row.key), [rows]);

  /**
   * A refetched chapter list can drop rows the selection still names, and a
   * bulk action on ids the reader can no longer see is the bug `retainSelection`
   * exists to stop. Pruned on the way OUT rather than written back into state:
   * the stored set is what the reader ticked, and a filter that removes a row
   * for a moment should not silently forget it was chosen.
   */
  const visible = useMemo(() => retainSelection(selection, keys), [keys, selection]);

  const pick = useCallback(
    (chapterKey: string, shift: boolean) => {
      setSelection((current) =>
        shift
          ? extendChapterSelection(current, chapterKey, keys)
          : toggleChapter(current, chapterKey),
      );
    },
    [keys],
  );

  const helpers = useMemo(() => {
    const next = nextChapters(rows, NEXT_BATCH_SIZE);
    const unread = unreadChapters(rows);
    const list = [
      { id: "next", label: `Next ${NEXT_BATCH_SIZE}`, keys: next },
      { id: "unread", label: "All unread", keys: unread },
    ];
    if (medium === "novel") {
      list.push({ id: "all", label: "Whole book", keys: everyChapter(rows) });
    }
    return list.filter((helper) => helper.keys.length > 0);
  }, [medium, rows]);

  const plan = useMemo(() => planDownload(rows, visible.ids), [rows, visible.ids]);
  const unsaved = useMemo(() => everyChapter(rows), [rows]);

  const begin = useCallback(() => setSelecting(true), []);
  const end = useCallback(() => {
    setSelecting(false);
    setSelection(EMPTY_CHAPTER_SELECTION);
  }, []);

  const startKeys = useCallback(
    (chapterKeys: readonly string[]) => {
      void downloads.download(chapterKeys);
    },
    [downloads],
  );

  const start = useCallback(() => {
    if (plan.length === 0) return;
    void downloads.download(plan).then(() => setSelection(EMPTY_CHAPTER_SELECTION));
  }, [downloads, plan]);

  return {
    downloads,
    selecting,
    begin,
    end,
    selection: visible,
    selectedCount: visible.ids.size,
    isSelected: (chapterKey: string) => visible.ids.has(chapterKey),
    pick,
    plan,
    unsaved,
    helpers,
    applyHelper: (helperKeys) => {
      setSelecting(true);
      setSelection((current) => addChapters(current, helperKeys));
    },
    stateOf: downloads.stateOf,
    start,
    startKeys,
    savedCount: rows.filter((row) => row.saved).length,
    total: rows.length,
  };
}
