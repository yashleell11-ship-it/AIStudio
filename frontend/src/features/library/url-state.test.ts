import { describe, expect, it } from "vitest";
import {
  DEFAULT_LIBRARY_QUERY,
  type LibraryQuery,
  hasActiveFilters,
  isDefaultLibraryQuery,
  libraryQuerySearchString,
  libraryQueryToListParams,
  libraryQueryToSearchParams,
  parseLibraryQuery,
} from "./url-state";

function parse(search: string): LibraryQuery {
  return parseLibraryQuery(new URLSearchParams(search));
}

function roundTrip(query: LibraryQuery): LibraryQuery {
  return parseLibraryQuery(libraryQueryToSearchParams(query));
}

describe("parseLibraryQuery", () => {
  it("gives the default view for an empty query string", () => {
    expect(parse("")).toEqual(DEFAULT_LIBRARY_QUERY);
  });

  it("reads every parameter GET /library/series accepts", () => {
    expect(
      parse(
        "search=solo&sort=year&status=reading&reading_status=completed" +
          "&is_favorite=true&language=ko&has_chapters=false" +
          "&collection_id=3&tag_id=7&library_id=2",
      ),
    ).toEqual({
      search: "solo",
      sort: "year",
      status: "reading",
      reading_status: "completed",
      is_favorite: true,
      language: "ko",
      has_chapters: false,
      collection_id: 3,
      tag_id: 7,
      library_id: 2,
    });
  });

  it("falls back to the default sort for a value the backend does not name", () => {
    // `title` was the old client-only alias; it sorted by sort_title while
    // claiming to be its own mode.
    expect(parse("sort=title").sort).toBe(DEFAULT_LIBRARY_QUERY.sort);
    expect(parse("sort=nonsense").sort).toBe(DEFAULT_LIBRARY_QUERY.sort);
  });

  it("drops a shelf status the backend never writes", () => {
    expect(parse("reading_status=on_hold").reading_status).toBeNull();
  });

  it("accepts both boolean spellings FastAPI does", () => {
    expect(parse("is_favorite=1").is_favorite).toBe(true);
    expect(parse("is_favorite=0").is_favorite).toBe(false);
    expect(parse("is_favorite=maybe").is_favorite).toBeNull();
  });

  it("ignores ids that are not positive integers", () => {
    expect(parse("tag_id=0").tag_id).toBeNull();
    expect(parse("tag_id=-4").tag_id).toBeNull();
    expect(parse("tag_id=1.5").tag_id).toBeNull();
    expect(parse("collection_id=abc").collection_id).toBeNull();
  });

  it("trims the search term and treats whitespace as absent", () => {
    expect(parse("search=%20%20solo%20").search).toBe("solo");
    expect(parse("search=%20%20").search).toBe("");
    expect(parse("language=%20%20").language).toBeNull();
  });

  it("survives a truncated or hand-edited URL", () => {
    expect(parse("sort=&status=&is_favorite=&tag_id=")).toEqual(DEFAULT_LIBRARY_QUERY);
  });
});

describe("libraryQueryToSearchParams", () => {
  it("omits everything at its default so the landing URL stays bare", () => {
    expect(libraryQuerySearchString(DEFAULT_LIBRARY_QUERY)).toBe("");
    expect(isDefaultLibraryQuery(DEFAULT_LIBRARY_QUERY)).toBe(true);
  });

  it("serializes false as a real filter, not as absent", () => {
    // `is_favorite=false` means "only non-favourites" server-side; dropping it
    // would silently widen the view.
    const query = { ...DEFAULT_LIBRARY_QUERY, is_favorite: false };
    expect(libraryQuerySearchString(query)).toBe("?is_favorite=false");
    expect(isDefaultLibraryQuery(query)).toBe(false);
  });

  it("emits keys in a fixed order so the same view is the same URL", () => {
    const query: LibraryQuery = {
      ...DEFAULT_LIBRARY_QUERY,
      tag_id: 7,
      search: "solo",
      sort: "author",
    };
    expect(libraryQuerySearchString(query)).toBe("?search=solo&sort=author&tag_id=7");
  });
});

describe("round trip", () => {
  const cases: Array<[string, LibraryQuery]> = [
    ["default", DEFAULT_LIBRARY_QUERY],
    ["search only", { ...DEFAULT_LIBRARY_QUERY, search: "tower of god" }],
    ["sort only", { ...DEFAULT_LIBRARY_QUERY, sort: "total_chapters" }],
    ["favourites off", { ...DEFAULT_LIBRARY_QUERY, is_favorite: false }],
    ["favourites on", { ...DEFAULT_LIBRARY_QUERY, is_favorite: true }],
    [
      "everything at once",
      {
        search: "a b",
        sort: "recent",
        status: "unread",
        reading_status: "reading",
        is_favorite: true,
        language: "ja",
        has_chapters: true,
        collection_id: 12,
        tag_id: 34,
        library_id: 5,
      },
    ],
  ];

  for (const [name, query] of cases) {
    it(`survives serialize → parse: ${name}`, () => {
      expect(roundTrip(query)).toEqual(query);
    });
  }

  it("is stable across a second trip, so the back button lands somewhere real", () => {
    const query: LibraryQuery = {
      ...DEFAULT_LIBRARY_QUERY,
      status: "reading",
      language: "ko",
    };
    const once = libraryQuerySearchString(query);
    expect(libraryQuerySearchString(roundTrip(query))).toBe(once);
  });
});

describe("hasActiveFilters", () => {
  it("ignores the search term, which has its own empty state", () => {
    expect(hasActiveFilters({ ...DEFAULT_LIBRARY_QUERY, search: "solo" })).toBe(false);
  });

  it("notices any narrowing filter", () => {
    expect(hasActiveFilters({ ...DEFAULT_LIBRARY_QUERY, is_favorite: true })).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_LIBRARY_QUERY, status: "unread" })).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_LIBRARY_QUERY, tag_id: 3 })).toBe(true);
  });
});

describe("libraryQueryToListParams", () => {
  it("sends nulls as absent rather than as literal nulls", () => {
    expect(
      libraryQueryToListParams(DEFAULT_LIBRARY_QUERY, { page: 1, per_page: 200 }),
    ).toEqual({
      page: 1,
      per_page: 200,
      sort: "updated",
      search: undefined,
      status: undefined,
      reading_status: undefined,
      collection_id: undefined,
      tag_id: undefined,
      library_id: undefined,
      is_favorite: undefined,
      language: undefined,
      has_chapters: undefined,
    });
  });

  it("drops the client-only 'all' sentinel, which the backend has no branch for", () => {
    const params = libraryQueryToListParams(
      { ...DEFAULT_LIBRARY_QUERY, status: "all" },
      { page: 1, per_page: 40 },
    );
    expect(params.status).toBeUndefined();
  });

  it("keeps is_favorite=false, which is a filter and not an absence", () => {
    const params = libraryQueryToListParams(
      { ...DEFAULT_LIBRARY_QUERY, is_favorite: false },
      { page: 1, per_page: 40 },
    );
    expect(params.is_favorite).toBe(false);
  });
});
