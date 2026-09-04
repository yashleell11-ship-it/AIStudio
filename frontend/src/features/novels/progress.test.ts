import { describe, expect, it } from "vitest";
import {
  activeParagraphIndex,
  bucketCount,
  bucketForParagraph,
  chapterPercent,
  MAX_PROGRESS_BUCKETS,
  nextProgressPush,
  paragraphForBucket,
  progressForParagraph,
} from "./progress";

describe("bucketCount", () => {
  it("gives a short chapter one bucket per paragraph", () => {
    expect(bucketCount(1)).toBe(1);
    expect(bucketCount(30)).toBe(30);
    expect(bucketCount(100)).toBe(100);
  });

  it("caps a long chapter so a bucket is never finer than ~1%", () => {
    expect(bucketCount(101)).toBe(MAX_PROGRESS_BUCKETS);
    expect(bucketCount(2400)).toBe(MAX_PROGRESS_BUCKETS);
  });

  it("never returns zero, so page_count is never a divide-by-zero", () => {
    expect(bucketCount(0)).toBe(1);
    expect(bucketCount(-5)).toBe(1);
    expect(bucketCount(Number.NaN)).toBe(1);
  });
});

describe("bucketForParagraph", () => {
  it("is 1-based — a fresh chapter reports bucket 1, never 0", () => {
    expect(bucketForParagraph(0, 40)).toBe(1);
    expect(bucketForParagraph(0, 900)).toBe(1);
  });

  it("maps the last paragraph to the last bucket", () => {
    expect(bucketForParagraph(39, 40)).toBe(40);
    expect(bucketForParagraph(899, 900)).toBe(MAX_PROGRESS_BUCKETS);
  });

  it("tracks the paragraph one-for-one while the chapter is short", () => {
    for (let index = 0; index < 30; index += 1) {
      expect(bucketForParagraph(index, 30)).toBe(index + 1);
    }
  });

  it("advances monotonically through a long chapter", () => {
    let previous = 0;
    for (let index = 0; index < 900; index += 1) {
      const bucket = bucketForParagraph(index, 900);
      expect(bucket).toBeGreaterThanOrEqual(previous);
      previous = bucket;
    }
    expect(previous).toBe(MAX_PROGRESS_BUCKETS);
  });

  it("clamps nonsense rather than reporting off the end", () => {
    expect(bucketForParagraph(-3, 40)).toBe(1);
    expect(bucketForParagraph(4000, 40)).toBe(40);
    expect(bucketForParagraph(0, 0)).toBe(1);
  });
});

describe("paragraphForBucket", () => {
  it("resumes at the FIRST paragraph of the bucket, never past it", () => {
    // 900 paragraphs over 100 buckets: bucket 2 starts at paragraph 9.
    expect(paragraphForBucket(1, 900)).toBe(0);
    expect(paragraphForBucket(2, 900)).toBe(9);
    expect(paragraphForBucket(100, 900)).toBe(891);
  });

  it("round-trips: resuming a bucket reports that same bucket", () => {
    for (const paragraphCount of [7, 30, 100, 313, 900, 2400]) {
      const buckets = bucketCount(paragraphCount);
      for (let bucket = 1; bucket <= buckets; bucket += 1) {
        const paragraph = paragraphForBucket(bucket, paragraphCount);
        expect(bucketForParagraph(paragraph, paragraphCount)).toBe(bucket);
      }
    }
  });

  it("clamps out-of-range buckets into the chapter", () => {
    expect(paragraphForBucket(0, 40)).toBe(0);
    expect(paragraphForBucket(-1, 40)).toBe(0);
    expect(paragraphForBucket(999, 40)).toBe(39);
    expect(paragraphForBucket(3, 0)).toBe(0);
  });
});

describe("activeParagraphIndex", () => {
  const offsets = [0, 120, 260, 400, 560];

  it("reports the paragraph the reading line is inside", () => {
    expect(activeParagraphIndex(offsets, 0)).toBe(0);
    expect(activeParagraphIndex(offsets, 119)).toBe(0);
    expect(activeParagraphIndex(offsets, 120)).toBe(1);
    expect(activeParagraphIndex(offsets, 399)).toBe(2);
    expect(activeParagraphIndex(offsets, 10_000)).toBe(4);
  });

  it("never goes below the first paragraph when scrolled above the text", () => {
    expect(activeParagraphIndex(offsets, -300)).toBe(0);
  });

  it("survives an unmeasured chapter", () => {
    expect(activeParagraphIndex([], 400)).toBe(0);
  });
});

describe("progressForParagraph", () => {
  it("packs a position into the last_page / page_count pair", () => {
    expect(progressForParagraph(0, 40)).toEqual({
      bucket: 1,
      buckets: 40,
      completed: false,
    });
  });

  it("marks the chapter complete only at the final bucket", () => {
    expect(progressForParagraph(38, 40).completed).toBe(false);
    expect(progressForParagraph(39, 40).completed).toBe(true);
    expect(progressForParagraph(899, 900).completed).toBe(true);
  });
});

describe("nextProgressPush", () => {
  it("sends a position that moves the reader forward", () => {
    const position = progressForParagraph(12, 40);
    expect(nextProgressPush(position, 5)).toBe(position);
  });

  it("never rewinds — scrolling back to re-read reports nothing", () => {
    const position = progressForParagraph(3, 40);
    expect(nextProgressPush(position, 12)).toBeNull();
    expect(nextProgressPush(position, 4)).toBeNull();
  });

  it("does not resend the position already stored", () => {
    const position = progressForParagraph(11, 40);
    expect(position.bucket).toBe(12);
    expect(nextProgressPush(position, 12)).toBeNull();
  });
});

describe("chapterPercent", () => {
  it("reads out as a percentage of the chapter", () => {
    expect(chapterPercent(1, 100)).toBe(1);
    expect(chapterPercent(50, 100)).toBe(50);
    expect(chapterPercent(40, 40)).toBe(100);
    expect(chapterPercent(3, 40)).toBe(8);
  });

  it("clamps rather than reporting over 100%", () => {
    expect(chapterPercent(120, 100)).toBe(100);
    expect(chapterPercent(-4, 100)).toBe(0);
    expect(chapterPercent(4, 0)).toBe(0);
  });
});
