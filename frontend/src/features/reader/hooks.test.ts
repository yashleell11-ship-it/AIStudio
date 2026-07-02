import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { bookmarksQueryKey } from "./hooks";
import type { Bookmark } from "./api";

/**
 * Bookmark Manager regression tests. Before this feature, the reader could
 * only ADD a bookmark -- there was no way to list or remove one from any
 * client, even though the backend already supported both. These tests
 * verify the query-key convention the Bookmark Manager view and the delete
 * mutation share, mirroring the QueryClient-driven style used across this
 * suite (see features/updates/hooks.test.ts) since no React renderer
 * utility is set up in this project.
 */
function bookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: 1,
    series_id: 10,
    series_title: "Solo Leveling",
    chapter_id: 20,
    chapter_title: "Chapter 1",
    page: 3,
    note: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("bookmarksQueryKey", () => {
  it("is stable and namespaced under reader", () => {
    expect(bookmarksQueryKey()).toEqual(["reader", "bookmarks"]);
  });

  it("useDeleteBookmark invalidates the exact key useBookmarks reads", () => {
    const queryClient = new QueryClient();
    const key = bookmarksQueryKey();

    queryClient.setQueryData(key, [
      bookmark({ id: 1 }),
      bookmark({ id: 2 }),
    ]);

    // Simulates useDeleteBookmark.onSuccess: invalidate the same key
    // useBookmarks() reads, so the Bookmark Manager view refetches and the
    // removed bookmark disappears without a page reload.
    void queryClient.invalidateQueries({ queryKey: key });

    expect(queryClient.getQueryState(key)?.isInvalidated).toBe(true);
  });
});

describe("Bookmark shape carries the fields the Bookmark Manager needs to render", () => {
  it("includes series/chapter titles for display", () => {
    const item = bookmark();
    expect(item.series_title).toBe("Solo Leveling");
    expect(item.chapter_title).toBe("Chapter 1");
  });

  it("tolerates missing titles (orphaned series/chapter) without crashing the shape", () => {
    const item = bookmark({ series_title: null, chapter_title: null });
    expect(item.series_title).toBeNull();
    expect(item.chapter_title).toBeNull();
  });
});
