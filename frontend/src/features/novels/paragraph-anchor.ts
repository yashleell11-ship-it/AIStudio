/**
 * A bookmark's exact spot in a chapter of prose, as pure functions of measured
 * paragraph offsets.
 *
 * The component's only job is to measure — `offsetsRef` already holds each
 * paragraph's distance from the top of the scroll container, one entry per
 * paragraph in paragraph order — so the capture and its inverse live here
 * where they can be tested without a DOM, exactly like `progress.ts` next to
 * them.
 *
 * The pair is inverse by construction: capture asks which paragraph the
 * reading line is in and how far through it, restore puts the reading line
 * back at that point. Anything else (rounding the fraction to a paragraph, or
 * restoring to a paragraph's top) turns "exactly where it left" into "roughly
 * where it left", which is what the whole design is trying to stop.
 */

import { fractionWithin, pointWithin, resolveAnchor } from "@/features/bookmarks";
import { activeParagraphIndex } from "./progress";

/** The exact spot a novel bookmark records. */
export interface ParagraphAnchor {
  /** 1-based paragraph index — the same index the server's snippet uses. */
  index: number;
  /** 0.0–1.0 through that paragraph. */
  fraction: number;
  /** Paragraphs in the chapter, which turns the pair into a percentage. */
  total: number;
}

/**
 * Where a paragraph ends, in scroll coordinates: the next paragraph's start,
 * or the end of the content for the last one.
 */
function paragraphEnd(
  offsets: readonly number[],
  index: number,
  contentEnd: number,
): number {
  return index + 1 < offsets.length ? offsets[index + 1] : contentEnd;
}

/**
 * The anchor to record for a reading line, or null when nothing is measured
 * yet — which is what keeps a bookmark taken on a still-loading chapter from
 * claiming "paragraph 1 of 0".
 */
export function captureParagraphAnchor(
  offsets: readonly number[],
  readingLine: number,
  contentEnd: number,
): ParagraphAnchor | null {
  if (offsets.length === 0) return null;
  const index = activeParagraphIndex(offsets, readingLine);
  return {
    index: index + 1,
    fraction: fractionWithin(
      readingLine,
      offsets[index],
      paragraphEnd(offsets, index, contentEnd),
    ),
    total: offsets.length,
  };
}

export interface ParagraphAnchorTarget {
  /** Where the reading line should be put, in scroll coordinates. */
  point: number;
  /** The recorded paragraph is gone; the nearest one was used (design §3). */
  stale: boolean;
}

/**
 * Where to put the reading line to restore an anchor, resolved against the
 * paragraphs this chapter has NOW.
 *
 * A source that re-splits its text — an aggregator merging a wall of dialogue,
 * a chapter republished shorter — moves every index after the change. Rather
 * than failing or silently jumping to the top, the nearest paragraph that
 * still exists is used and `stale` says so, for the reader to be told quietly.
 */
export function restoreParagraphAnchor(
  offsets: readonly number[],
  anchor: { index: number; fraction: number },
  contentEnd: number,
): ParagraphAnchorTarget | null {
  if (offsets.length === 0) return null;
  const resolved = resolveAnchor(anchor, offsets.length);
  const start = offsets[resolved.index - 1];
  if (start == null) return null;
  return {
    point: pointWithin(
      resolved.fraction,
      start,
      paragraphEnd(offsets, resolved.index - 1, contentEnd),
    ),
    stale: resolved.stale,
  };
}
