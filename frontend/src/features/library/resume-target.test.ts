import { describe, expect, it } from "vitest";
import {
  compareChapters,
  hasStartedReading,
  resumeTarget,
  type ResumeProgress,
} from "./resume-target";

type Row = { key: string; number: number | null };

const chapters: Row[] = [
  { key: "c1", number: 1 },
  { key: "c2", number: 2 },
  { key: "c3", number: 3 },
];

function done(page = 20): ResumeProgress {
  return { last_page: page, is_completed: true };
}

function partway(page: number): ResumeProgress {
  return { last_page: page, is_completed: false };
}

describe("resumeTarget", () => {
  it("returns null for a series with no chapters", () => {
    expect(resumeTarget([], {})).toBeNull();
  });

  it("offers the first chapter of an untouched series", () => {
    expect(resumeTarget(chapters, {})).toEqual({
      chapter: chapters[0],
      page: 1,
    });
  });

  it("takes the FURTHEST unfinished chapter, not the earliest", () => {
    // Chapter 1 was skimmed and abandoned; 3 is where reading actually is.
    const target = resumeTarget(chapters, {
      c1: partway(4),
      c2: done(),
      c3: partway(7),
    });
    expect(target).toEqual({ chapter: chapters[2], page: 7 });
  });

  it("moves on to the first unread chapter once the read ones are finished", () => {
    // The case that sent the phone back to chapter 1: finish 2 cleanly, close
    // the reader on its last page, and there is no unfinished row anywhere.
    const target = resumeTarget(chapters, { c1: done(), c2: done() });
    expect(target).toEqual({ chapter: chapters[2], page: 1 });
  });

  it("offers the last chapter when every chapter is finished", () => {
    const target = resumeTarget(chapters, {
      c1: done(),
      c2: done(),
      c3: done(),
    });
    expect(target).toEqual({ chapter: chapters[2], page: 1 });
  });

  it("resolves the rule on chapter NUMBER, not on listing order", () => {
    const newestFirst: Row[] = [
      { key: "c3", number: 3 },
      { key: "c2", number: 2 },
      { key: "c1", number: 1 },
    ];
    const target = resumeTarget(newestFirst, {
      c1: partway(2),
      c3: partway(9),
    });
    expect(target).toEqual({ chapter: newestFirst[0], page: 9 });
  });

  it("opens at page 1 when a stored position is missing or nonsensical", () => {
    expect(resumeTarget(chapters, { c1: partway(0) })?.page).toBe(1);
    expect(resumeTarget(chapters, { c1: partway(-3) })?.page).toBe(1);
  });

  it("ignores progress rows for chapters the series no longer lists", () => {
    const target = resumeTarget(chapters, { gone: partway(12) });
    expect(target).toEqual({ chapter: chapters[0], page: 1 });
  });

  it("sorts unnumbered chapters before numbered ones", () => {
    const mixed: Row[] = [
      { key: "n", number: null },
      { key: "c1", number: 1 },
    ];
    expect([...mixed].sort(compareChapters)[0].key).toBe("n");
    expect(resumeTarget(mixed, {})?.chapter.key).toBe("n");
  });
});

describe("hasStartedReading", () => {
  it("is false for a series with no progress at all", () => {
    expect(hasStartedReading({})).toBe(false);
  });

  it("is true once any chapter has a row, finished or not", () => {
    expect(hasStartedReading({ c1: done() })).toBe(true);
    expect(hasStartedReading({ c1: partway(3) })).toBe(true);
  });
});
