import { describe, expect, it } from "vitest";
import { ApiError } from "@/types/api";
import { resolveChapterListState } from "./chapter-list-state";

// The shapes `services/http.ts` actually throws — an unreachable server is a
// status-0 `network_error`, not a distinct exception type.
const NETWORK_ERROR = new ApiError(0, {
  code: "network_error",
  message: "Can't reach ManhwaManiacs right now.",
});
const SERVER_ERROR = new ApiError(500, { code: "boom", message: "Something broke." });

function input(overrides: Partial<Parameters<typeof resolveChapterListState>[0]> = {}) {
  return {
    isLoading: false,
    error: null as unknown,
    chapterCount: 0,
    reportedChapterCount: 0,
    ...overrides,
  };
}

describe("resolveChapterListState", () => {
  it("reports loading before anything else", () => {
    expect(
      resolveChapterListState(input({ isLoading: true, error: SERVER_ERROR })),
    ).toBe("loading");
  });

  it("keeps the shared offline/error split", () => {
    expect(resolveChapterListState(input({ error: NETWORK_ERROR }))).toBe("offline");
    expect(resolveChapterListState(input({ error: SERVER_ERROR }))).toBe("error");
  });

  it("calls an empty answer 'unavailable' when the source says chapters exist", () => {
    expect(
      resolveChapterListState(input({ chapterCount: 0, reportedChapterCount: 214 })),
    ).toBe("unavailable");
  });

  it("calls an empty answer 'empty' when the source claims none either", () => {
    expect(
      resolveChapterListState(input({ chapterCount: 0, reportedChapterCount: 0 })),
    ).toBe("empty");
  });

  it("reports content whenever chapters came back, whatever the summary claimed", () => {
    expect(
      resolveChapterListState(input({ chapterCount: 12, reportedChapterCount: 0 })),
    ).toBe("content");
    expect(
      resolveChapterListState(input({ chapterCount: 12, reportedChapterCount: 214 })),
    ).toBe("content");
  });
});
