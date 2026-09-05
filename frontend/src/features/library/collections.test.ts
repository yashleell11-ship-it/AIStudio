import { describe, expect, it } from "vitest";
import {
  collectionMemberKeys,
  collectionUpdateBody,
  resolveCollectionMembers,
  seriesRefKey,
} from "./collections";
import type { CollectionSeriesRef, FollowedSeries } from "./types";

function ref(sourceId: string, seriesKey: string, sortOrder = 0): CollectionSeriesRef {
  return { source_id: sourceId, series_key: seriesKey, sort_order: sortOrder };
}

function series(
  id: number,
  sourceId: string,
  seriesKey: string,
  title: string,
): FollowedSeries {
  return {
    id,
    source_id: sourceId,
    series_key: seriesKey,
    title,
    cover_url: `/sources/${sourceId}/series/${seriesKey}/cover`,
    is_favorite: false,
    reading_status: "reading",
    notify: true,
    sort_order: 0,
    content_rating: "safe",
    rating: "safe",
    mature_override: null,
    chapter_count: 12,
    last_checked_at: null,
    created_at: null,
    updated_at: null,
  };
}

describe("seriesRefKey", () => {
  it("keeps two sources' identical series keys apart", () => {
    expect(seriesRefKey("asura", "solo-leveling")).not.toBe(
      seriesRefKey("cmanhua", "solo-leveling"),
    );
  });
});

describe("collectionMemberKeys", () => {
  it("keys every ref for membership lookups", () => {
    const keys = collectionMemberKeys([ref("asura", "a"), ref("cmanhua", "b")]);
    expect(keys.has("asura:a")).toBe(true);
    expect(keys.has("cmanhua:b")).toBe(true);
    expect(keys.has("asura:b")).toBe(false);
  });

  it("is empty for a collection with nothing in it", () => {
    expect(collectionMemberKeys([]).size).toBe(0);
  });
});

describe("resolveCollectionMembers", () => {
  const followed = [
    series(1, "asura", "a", "Alpha"),
    series(2, "cmanhua", "b", "Beta"),
  ];

  it("joins each ref to its followed row", () => {
    const members = resolveCollectionMembers([ref("cmanhua", "b")], followed);
    expect(members).toHaveLength(1);
    expect(members[0].series?.id).toBe(2);
    expect(members[0].label).toBe("Beta");
  });

  it("keeps collection order rather than the followed order", () => {
    const members = resolveCollectionMembers(
      [ref("cmanhua", "b"), ref("asura", "a")],
      followed,
    );
    expect(members.map((member) => member.label)).toEqual(["Beta", "Alpha"]);
  });

  // Unfollowing does not clear collection membership, so this row is the only
  // one a remove UI has to be able to reach — dropping it would strand it.
  it("still returns a ref whose series is no longer followed", () => {
    const members = resolveCollectionMembers([ref("asura", "gone")], followed);
    expect(members).toHaveLength(1);
    expect(members[0].series).toBeNull();
    expect(members[0].label).toBe("gone");
  });

  it("does not match a series key that belongs to another source", () => {
    const members = resolveCollectionMembers([ref("cmanhua", "a")], followed);
    expect(members[0].series).toBeNull();
  });
});

describe("collectionUpdateBody", () => {
  const current = { name: "Weeknights", description: "Short reads" };

  it("returns null when nothing was touched", () => {
    expect(
      collectionUpdateBody(current, {
        name: "Weeknights",
        description: "Short reads",
      }),
    ).toBeNull();
  });

  it("sends only the renamed field", () => {
    expect(
      collectionUpdateBody(current, {
        name: "Weeknight Reads",
        description: "Short reads",
      }),
    ).toEqual({ name: "Weeknight Reads" });
  });

  it("treats surrounding whitespace as no change at all", () => {
    expect(
      collectionUpdateBody(current, {
        name: "  Weeknights  ",
        description: "  Short reads  ",
      }),
    ).toBeNull();
  });

  it("trims a name it does send", () => {
    expect(
      collectionUpdateBody(current, {
        name: "  Weekend  ",
        description: "Short reads",
      }),
    ).toEqual({ name: "Weekend" });
  });

  // "   " clears the backend's min_length=1 and is only stripped afterwards,
  // which would commit a collection with no name.
  it("never sends a blank name", () => {
    expect(
      collectionUpdateBody(current, { name: "   ", description: "Short reads" }),
    ).toBeNull();
  });

  // The form disables Save on a blank name of its own accord; the body simply
  // drops the name rather than letting an empty one ride along with the rest.
  it("drops a blank name without losing the other change", () => {
    expect(
      collectionUpdateBody(current, { name: "", description: "Long reads" }),
    ).toEqual({ description: "Long reads" });
  });

  // The backend ignores a null description, so "" is the only way to clear one.
  it("sends an empty string to clear the description", () => {
    expect(
      collectionUpdateBody(current, { name: "Weeknights", description: "" }),
    ).toEqual({ description: "" });
  });

  it("counts adding a description to a collection that had none", () => {
    expect(
      collectionUpdateBody(
        { name: "Weeknights", description: null },
        { name: "Weeknights", description: "Short reads" },
      ),
    ).toEqual({ description: "Short reads" });
  });

  it("leaves an absent description alone", () => {
    expect(
      collectionUpdateBody(
        { name: "Weeknights", description: null },
        { name: "Weeknights", description: "" },
      ),
    ).toBeNull();
  });
});
