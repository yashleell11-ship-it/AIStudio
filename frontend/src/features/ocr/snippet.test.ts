import { describe, expect, it } from "vitest";
import { parseSnippet } from "./snippet";

describe("parseSnippet", () => {
  it("returns a single plain segment when there are no markers", () => {
    expect(parseSnippet("just some dialogue")).toEqual([
      { text: "just some dialogue", highlight: false },
    ]);
  });

  it("splits a highlighted term into plain and highlighted runs", () => {
    expect(parseSnippet("the <mark>hero</mark> speaks")).toEqual([
      { text: "the ", highlight: false },
      { text: "hero", highlight: true },
      { text: " speaks", highlight: false },
    ]);
  });

  it("handles multiple highlights", () => {
    expect(parseSnippet("<mark>a</mark> and <mark>b</mark>")).toEqual([
      { text: "a", highlight: true },
      { text: " and ", highlight: false },
      { text: "b", highlight: true },
    ]);
  });

  it("does not emit empty highlighted segments", () => {
    expect(parseSnippet("x<mark></mark>y")).toEqual([
      { text: "x", highlight: false },
      { text: "y", highlight: false },
    ]);
  });

  it("treats an unbalanced marker as plain text", () => {
    expect(parseSnippet("dangling <mark>open")).toEqual([
      { text: "dangling <mark>open", highlight: false },
    ]);
  });

  it("does not interpret non-mark markup as HTML (kept as literal text)", () => {
    const segments = parseSnippet("<script>alert(1)</script> <mark>hit</mark>");
    expect(segments).toEqual([
      { text: "<script>alert(1)</script> ", highlight: false },
      { text: "hit", highlight: true },
    ]);
  });
});
