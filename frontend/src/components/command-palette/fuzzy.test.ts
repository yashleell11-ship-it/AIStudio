import { describe, expect, it } from "vitest";
import { fuzzyMatch, fuzzyMatchAny, highlightSegments } from "./fuzzy";

function score(query: string, text: string): number {
  const match = fuzzyMatch(query, text);
  expect(match, `expected ${query} to match ${text}`).not.toBeNull();
  return match!.score;
}

describe("fuzzyMatch", () => {
  it("matches an empty query against anything, neutrally", () => {
    expect(fuzzyMatch("", "Downloads")).toEqual({ score: 0, indices: [] });
    expect(fuzzyMatch("   ", "Downloads")).toEqual({ score: 0, indices: [] });
  });

  it("rejects text missing a query character", () => {
    expect(fuzzyMatch("zz", "Downloads")).toBeNull();
    expect(fuzzyMatch("anything", "")).toBeNull();
  });

  it("requires the query characters in order", () => {
    expect(fuzzyMatch("ba", "abc")).toBeNull();
    expect(fuzzyMatch("ab", "abc")).not.toBeNull();
  });

  it("is case-insensitive", () => {
    expect(fuzzyMatch("DOWN", "Downloads")).not.toBeNull();
    expect(fuzzyMatch("down", "DOWNLOADS")).not.toBeNull();
  });

  it("reports the matched indices into the original text", () => {
    expect(fuzzyMatch("dl", "Downloads")?.indices).toEqual([0, 4]);
    expect(fuzzyMatch("load", "Downloads")?.indices).toEqual([4, 5, 6, 7]);
  });

  it("ranks a prefix above a mid-word substring", () => {
    expect(score("read", "Reader")).toBeGreaterThan(score("read", "Continue Reading"));
  });

  it("ranks a word-start substring above an arbitrary one", () => {
    expect(score("man", "Solo Man Levelling")).toBeGreaterThan(
      score("man", "Romance Manwha"),
    );
  });

  it("ranks a contiguous run above the same characters scattered", () => {
    expect(score("sett", "Settings")).toBeGreaterThan(score("sett", "Save Every Tag Type"));
  });

  it("prefers the shallower of two prefix matches", () => {
    // "Library" starts at 0, "My Library" at 3 — the leading-skip penalty is
    // what keeps the exact destination on top.
    expect(score("lib", "Library")).toBeGreaterThan(score("lib", "My Library"));
  });

  it("finds initials across words", () => {
    const match = fuzzyMatch("sl", "Solo Levelling");
    expect(match).not.toBeNull();
    expect(match!.indices).toEqual([0, 5]);
  });

  it("aligns on word starts rather than on the leftmost characters", () => {
    // "Tales of Terror": scanning greedily would take the `o` of "**o**f" only
    // by luck; the `a` of "T**a**les" is what a leftmost scan reaches first for
    // similar queries. The DP picks the initials.
    expect(fuzzyMatch("tot", "Tales of Terror")?.indices).toEqual([0, 6, 9]);
    expect(fuzzyMatch("tog", "The Origin of Gods")?.indices).toEqual([0, 4, 14]);
  });

  it("prefers a contiguous run over a scattered initialism", () => {
    // "**To**wer of **G**od", not "**T**ower **o**f **G**od" — a run of
    // adjacent characters is stronger evidence than two word starts, and the
    // caller only ever compares this score with other candidates' scores.
    expect(fuzzyMatch("tog", "Tower of God")?.indices).toEqual([0, 1, 9]);
  });

  it("still matches when no word-start alignment exists", () => {
    expect(fuzzyMatch("owe", "Tower")?.indices).toEqual([1, 2, 3]);
  });
});

describe("fuzzyMatchAny", () => {
  it("falls back to secondary text when the title does not match", () => {
    const match = fuzzyMatchAny("shelf", "Library", ["shelf", "books"]);
    expect(match).not.toBeNull();
    // A keyword hit highlights nothing — the matched characters are not in the
    // string being rendered.
    expect(match!.indices).toEqual([]);
  });

  it("returns null only when nothing matches", () => {
    expect(fuzzyMatchAny("zzz", "Library", ["shelf"])).toBeNull();
  });

  it("keeps a title hit ahead of another command's keyword hit", () => {
    const onTitle = fuzzyMatchAny("down", "Downloads", []);
    const onKeyword = fuzzyMatchAny("down", "Queue", ["downloads"]);
    expect(onTitle!.score).toBeGreaterThan(onKeyword!.score);
  });

  it("keeps the title's indices when the title also matches", () => {
    const match = fuzzyMatchAny("lib", "Library", ["shelf"]);
    expect(match!.indices).toEqual([0, 1, 2]);
  });
});

describe("highlightSegments", () => {
  it("returns one unmatched segment when nothing matched", () => {
    expect(highlightSegments("Downloads", [])).toEqual([
      { text: "Downloads", match: false },
    ]);
  });

  it("splits a leading match", () => {
    expect(highlightSegments("Downloads", [0, 1])).toEqual([
      { text: "Do", match: true },
      { text: "wnloads", match: false },
    ]);
  });

  it("splits scattered matches", () => {
    expect(highlightSegments("Downloads", [0, 5])).toEqual([
      { text: "D", match: true },
      { text: "ownl", match: false },
      { text: "o", match: true },
      { text: "ads", match: false },
    ]);
  });

  it("reassembles into the original text", () => {
    const segments = highlightSegments("Solo Levelling", [0, 5, 6]);
    expect(segments.map((segment) => segment.text).join("")).toBe("Solo Levelling");
  });
});
