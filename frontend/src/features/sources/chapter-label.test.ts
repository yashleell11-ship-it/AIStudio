import { describe, expect, it } from "vitest";
import { chapterLabel } from "./chapter-label";

describe("chapterLabel", () => {
  it("leads with the canonical chapter number and shows the title beneath", () => {
    expect(chapterLabel({ number: 134, title: "The Culprit (7)" })).toEqual({
      primary: "Chapter 134",
      secondary: "The Culprit (7)",
    });
    expect(
      chapterLabel({ number: 135, title: "Heavenly Demon Inauguration (1)" }),
    ).toEqual({
      primary: "Chapter 135",
      secondary: "Heavenly Demon Inauguration (1)",
    });
  });

  it("does not repeat the backend's 'Chapter N' fallback title", () => {
    expect(chapterLabel({ number: 133, title: "Chapter 133" })).toEqual({
      primary: "Chapter 133",
      secondary: null,
    });
  });

  it("strips a redundant 'Chapter N' prefix from titles (e.g. MangaKatana)", () => {
    expect(chapterLabel({ number: 12, title: "Chapter 12: The Hunt" })).toEqual({
      primary: "Chapter 12",
      secondary: "The Hunt",
    });
    expect(chapterLabel({ number: 12, title: "chapter 12 - The Hunt" })).toEqual({
      primary: "Chapter 12",
      secondary: "The Hunt",
    });
    // A decimal continuation is a different chapter, not a redundant prefix.
    expect(chapterLabel({ number: 12, title: "Chapter 12.5 Special" })).toEqual({
      primary: "Chapter 12",
      secondary: "Chapter 12.5 Special",
    });
    expect(chapterLabel({ number: 12, title: "Chapter 125" })).toEqual({
      primary: "Chapter 12",
      secondary: "Chapter 125",
    });
  });

  it("strips a BARE ordinal prefix (Royal Road: '1. Good Morning Brother')", () => {
    expect(
      chapterLabel({ number: 1, title: "1. Good Morning Brother" }),
    ).toEqual({ primary: "Chapter 1", secondary: "Good Morning Brother" });
    expect(chapterLabel({ number: 12, title: "12 - The Hunt" })).toEqual({
      primary: "Chapter 12",
      secondary: "The Hunt",
    });
    expect(chapterLabel({ number: 12, title: "12) The Hunt" })).toEqual({
      primary: "Chapter 12",
      secondary: "The Hunt",
    });
    expect(chapterLabel({ number: 12.5, title: "12.5: Interlude" })).toEqual({
      primary: "Chapter 12.5",
      secondary: "Interlude",
    });
    expect(chapterLabel({ number: 7, title: "7." })).toEqual({
      primary: "Chapter 7",
      secondary: null,
    });
    expect(chapterLabel({ number: 7, title: "7" })).toEqual({
      primary: "Chapter 7",
      secondary: null,
    });
  });

  it("never mistakes another number for the chapter's own", () => {
    // The leading digits are part of the title, not an ordinal.
    expect(chapterLabel({ number: 1, title: "1000 Years of Solitude" })).toEqual({
      primary: "Chapter 1",
      secondary: "1000 Years of Solitude",
    });
    expect(chapterLabel({ number: 12, title: "125. The Hunt" })).toEqual({
      primary: "Chapter 12",
      secondary: "125. The Hunt",
    });
    // A decimal continuation is a different chapter — taking "12" and the dot
    // as a separator would leave the row reading "5 Special".
    expect(chapterLabel({ number: 12, title: "12.5 Special" })).toEqual({
      primary: "Chapter 12",
      secondary: "12.5 Special",
    });
  });

  it("treats empty titles as number-only chapters", () => {
    expect(chapterLabel({ number: 12, title: "" })).toEqual({
      primary: "Chapter 12",
      secondary: null,
    });
    expect(chapterLabel({ number: 12, title: "   " })).toEqual({
      primary: "Chapter 12",
      secondary: null,
    });
    expect(chapterLabel({ number: 12, title: null })).toEqual({
      primary: "Chapter 12",
      secondary: null,
    });
  });

  it("falls back to the title only when the number is missing", () => {
    expect(chapterLabel({ number: null, title: "Oneshot" })).toEqual({
      primary: "Oneshot",
      secondary: null,
    });
    expect(chapterLabel({ number: null, title: "" })).toEqual({
      primary: "Chapter",
      secondary: null,
    });
  });
});
