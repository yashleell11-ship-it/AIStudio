import { describe, expect, it } from "vitest";
import { ApiError } from "@/types/api";
import {
  migrationConflictTrackerId,
  migrationSummary,
  parseChapterOffset,
  stalePreviewFromError,
} from "./migration";
import type { MigrationPlan } from "./types";

function plan(overrides: Partial<MigrationPlan> = {}): MigrationPlan {
  return {
    tracker_id: 4,
    from: { source: "asura", series_id: "old-slug" },
    to: { source: "bato", series_id: "new-slug" },
    old_catalog: "ok",
    chapter_map: [],
    unmatched_source_chapters: [],
    target_only_chapters: [],
    counts: { old: 10, new: 12, matched: 9, dropped: 1 },
    chapter_map_hash: "deadbeef",
    warnings: [],
    sibling_trackers: [],
    notifications_rewritten: 0,
    notifications_dropped: 0,
    downloads_relinked: 0,
    merged_into_tracker_id: null,
    applied: false,
    ...overrides,
  };
}

describe("migrationConflictTrackerId", () => {
  it("extracts the existing follow from a 409 conflict", () => {
    const error = new ApiError(409, {
      code: "tracker_target_already_followed",
      message: "You already follow that series on that source.",
      details: { existing_tracker_id: 17, hint: "Retry with merge=true." },
    });
    expect(migrationConflictTrackerId(error)).toBe(17);
  });

  it("ignores unrelated errors", () => {
    expect(
      migrationConflictTrackerId(
        new ApiError(502, { code: "migration_target_unreachable", message: "down" }),
      ),
    ).toBeNull();
    expect(migrationConflictTrackerId(new Error("boom"))).toBeNull();
  });

  it("returns null when the conflict carries no usable tracker id", () => {
    const error = new ApiError(409, {
      code: "tracker_target_already_followed",
      message: "conflict",
      details: { existing_tracker_id: "17" },
    });
    expect(migrationConflictTrackerId(error)).toBeNull();
  });
});

describe("stalePreviewFromError", () => {
  it("returns the recomputed plan the server sent instead of applying a stale map", () => {
    const fresh = plan({ chapter_map_hash: "cafebabe" });
    const error = new ApiError(409, {
      code: "migration_stale",
      message: "The target's chapter list changed since the preview.",
      details: { preview: fresh },
    });
    expect(stalePreviewFromError(error)).toEqual(fresh);
  });

  it("ignores a conflict that is not a stale preview", () => {
    expect(
      stalePreviewFromError(
        new ApiError(409, {
          code: "tracker_target_already_followed",
          message: "conflict",
          details: { existing_tracker_id: 3 },
        }),
      ),
    ).toBeNull();
  });

  it("returns null when the payload is not a plan", () => {
    const error = new ApiError(409, {
      code: "migration_stale",
      message: "stale",
      details: { preview: { counts: {} } },
    });
    expect(stalePreviewFromError(error)).toBeNull();
  });
});

describe("migrationSummary", () => {
  it("states what carries over and what does not", () => {
    expect(migrationSummary({ old: 430, new: 512, matched: 412, dropped: 18 })).toBe(
      "412 of 430 chapters map onto the target's 512 · 18 cannot be carried over",
    );
  });

  it("says so when nothing is lost", () => {
    expect(migrationSummary({ old: 10, new: 10, matched: 10, dropped: 0 })).toBe(
      "10 of 10 chapters map onto the target's 10 · nothing is left behind",
    );
  });
});

describe("parseChapterOffset", () => {
  it("treats an empty field as no offset", () => {
    expect(parseChapterOffset("")).toBe(0);
    expect(parseChapterOffset("   ")).toBe(0);
  });

  it("accepts negative and fractional offsets", () => {
    expect(parseChapterOffset("-120")).toBe(-120);
    expect(parseChapterOffset("0.5")).toBe(0.5);
  });

  it("rejects input that is not a number, rather than silently sending 0", () => {
    expect(parseChapterOffset("abc")).toBeNull();
    expect(parseChapterOffset("1,5")).toBeNull();
  });
});
