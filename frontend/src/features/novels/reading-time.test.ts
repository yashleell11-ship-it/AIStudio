import { describe, expect, it } from "vitest";
import {
  countWords,
  formatChapterLength,
  formatReadingTime,
  formatWordCount,
  readingMinutes,
  WORDS_PER_MINUTE,
} from "./reading-time";

describe("readingMinutes", () => {
  it("estimates at 250 wpm", () => {
    expect(WORDS_PER_MINUTE).toBe(250);
    expect(readingMinutes(250)).toBe(1);
    expect(readingMinutes(2500)).toBe(10);
    expect(readingMinutes(3000)).toBe(12);
  });

  it("rounds a part-minute chapter up to a minute rather than to zero", () => {
    expect(readingMinutes(40)).toBe(1);
    expect(readingMinutes(1)).toBe(1);
  });

  it("says nothing for a chapter with no words", () => {
    expect(readingMinutes(0)).toBe(0);
    expect(readingMinutes(-10)).toBe(0);
    expect(readingMinutes(Number.NaN)).toBe(0);
  });
});

describe("formatReadingTime", () => {
  it("labels the estimate as an estimate", () => {
    expect(formatReadingTime(2000)).toBe("~8 min");
  });

  it("switches to hours past 90 minutes", () => {
    expect(formatReadingTime(90 * 250)).toBe("~90 min");
    expect(formatReadingTime(91 * 250)).toBe("~1 h 31 min");
    expect(formatReadingTime(120 * 250)).toBe("~2 h");
  });

  it("is null when there is nothing to estimate", () => {
    expect(formatReadingTime(0)).toBeNull();
  });
});

describe("formatWordCount", () => {
  it("separates thousands and respects the singular", () => {
    expect(formatWordCount(1)).toBe("1 word");
    expect(formatWordCount(940)).toBe("940 words");
    expect(formatWordCount(12400)).toBe(`${(12400).toLocaleString()} words`);
  });

  it("is null for a chapter that reported nothing", () => {
    expect(formatWordCount(0)).toBeNull();
    expect(formatWordCount(Number.NaN)).toBeNull();
  });
});

describe("formatChapterLength", () => {
  it("is the one line a novel chapter row shows instead of a page count", () => {
    expect(formatChapterLength(2000)).toBe("2,000 words · ~8 min");
  });

  it("says nothing at all when the length is unknown", () => {
    expect(formatChapterLength(null)).toBeNull();
    expect(formatChapterLength(undefined)).toBeNull();
    expect(formatChapterLength(0)).toBeNull();
  });
});

describe("countWords", () => {
  it("counts across paragraphs, ignoring blank ones", () => {
    expect(countWords(["one two three", "", "  ", "four five"])).toBe(5);
  });

  it("treats any run of whitespace as one separator", () => {
    expect(countWords(["a\n\tb   c"])).toBe(3);
    expect(countWords([])).toBe(0);
  });
});
