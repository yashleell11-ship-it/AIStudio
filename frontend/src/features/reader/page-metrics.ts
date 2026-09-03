/**
 * Continuous-strip layout math and the measured-height feedback that keeps the
 * virtualizer's estimates honest.
 *
 * A webtoon page reports no intrinsic dimensions, so the first estimate for
 * every page is a fixed-aspect guess. Once real pages are measured, the average
 * measured height is a far better guess for the ones still off screen than the
 * guess — feeding it back stops `getTotalSize()` from lurching as the reader
 * scrolls, which is what makes scrolling "hit air" or reveal a seam.
 */

/** The exact top offset of every page in a flush (or gapped) strip. */
export function stripOffsets(heights: readonly number[], gap = 0): number[] {
  const offsets: number[] = [];
  let running = 0;
  for (let i = 0; i < heights.length; i += 1) {
    offsets.push(running);
    running += Math.max(0, heights[i]) + (i < heights.length - 1 ? Math.max(0, gap) : 0);
  }
  return offsets;
}

/** Total scroll height of the strip: every page, plus a gap between each pair. */
export function stripHeight(heights: readonly number[], gap = 0): number {
  if (heights.length === 0) return 0;
  const pages = heights.reduce((sum, h) => sum + Math.max(0, h), 0);
  const gaps = Math.max(0, gap) * (heights.length - 1);
  return pages + gaps;
}

export interface HeightSamples {
  /** Sum of every measured page height. */
  total: number;
  /** Number of distinct pages measured. */
  count: number;
}

export const EMPTY_HEIGHT_SAMPLES: HeightSamples = { total: 0, count: 0 };

/**
 * Fold a fresh measurement in, replacing any previous sample for the same page
 * so a re-measure (image reload, resize) does not double-count.
 */
export function recordHeight(
  samples: HeightSamples,
  previousHeightForPage: number | undefined,
  measuredHeight: number,
): HeightSamples {
  if (!(measuredHeight > 0)) return samples;
  if (previousHeightForPage != null) {
    return {
      total: samples.total - previousHeightForPage + measuredHeight,
      count: samples.count,
    };
  }
  return { total: samples.total + measuredHeight, count: samples.count + 1 };
}

/**
 * The best height estimate for an unmeasured page: the running average of what
 * has been measured, or `fallback` (the fixed-aspect guess) until there is a
 * sample to go on.
 */
export function estimateFromSamples(samples: HeightSamples, fallback: number): number {
  if (samples.count === 0) return fallback;
  return samples.total / samples.count;
}
