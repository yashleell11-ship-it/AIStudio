import { describe, expect, it } from "vitest";
import type { SeriesId } from "@/types/api";
import { libraryReadAllHref } from "./read-all-link";

const ref: SeriesId = { sourceId: "asurascans", seriesKey: "series/one" };

describe("libraryReadAllHref", () => {
  it("starts at the top of a series the reader has not opened", () => {
    expect(libraryReadAllHref(ref, 40, null, false)).toBe(
      "/read-all/asurascans/series%2Fone",
    );
  });

  it("resumes where the reader left off", () => {
    expect(libraryReadAllHref(ref, 40, "chapters/12", false)).toBe(
      "/read-all/asurascans/series%2Fone?from=chapters%2F12",
    );
  });

  it("has nothing to read through in a one-chapter series", () => {
    expect(libraryReadAllHref(ref, 1, null, false)).toBeNull();
    expect(libraryReadAllHref(ref, 0, null, false)).toBeNull();
  });

  it("is not offered for prose, which has no page strip to run", () => {
    expect(libraryReadAllHref(ref, 40, null, true)).toBeNull();
  });

  it("waits rather than guessing while the source kind is unknown", () => {
    expect(libraryReadAllHref(ref, 40, "chapters/12", undefined)).toBeNull();
  });
});
