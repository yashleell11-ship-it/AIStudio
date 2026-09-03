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
        "search=solo&sort=title&status=reading&reading_status=completed&is_favorite=true",
      ),
    ).toEqual({
      search: "solo",
      sort: "title",
      status: "reading",
      reading_status: "completed",
      is_favorite: true,
    });
  });

  it("falls back to the default sort for a value the backend does not name", () => {
    expect(parse("sort=author").sort).toBe(DEFAULT_LIBRARY_QUERY.sort);
    expect(parse("sort=nonsense").sort).toBe(DEFAULT_LIBRARY_QUERY.sort);
  });

  it("drops a shelf status the backend never writes", () => {
    expect(parse("reading_status=nonsense").reading_status).toBeNull();
    expect(parse("reading_status=on_hold").reading_status).toBe("on_hold");
  });

  it("accepts both boolean spellings FastAPI does", () => {
    expect(parse("is_favorite=1").is_favorite).toBe(true);
    expect(parse("is_favorite=0").is_favorite).toBe(false);
    expect(parse("is_favorite=maybe").is_favorite).toBeNull();
  });

  it("trims the search term and treats whitespace as absent", () => {
    expect(parse("search=%20%20solo%20").search).toBe("solo");
    expect(parse("search=%20%20").search).toBe("");
  });

  it("survives a truncated or hand-edited URL", () => {
    expect(parse("sort=&status=&is_favorite=")).toEqual(DEFAULT_LIBRARY_QUERY);
  });
});

describe("libraryQueryToSearchParams", () => {
  it("omits everything at its default so the landing URL stays bare", () => {
    expect(libraryQuerySearchString(DEFAULT_LIBRARY_QUERY)).toBe("");
    expect(isDefaultLibraryQuery(DEFAULT_LIBRARY_QUERY)).toBe(true);
  });

  it("serializes false as a real filter, not as absent", () => {
    const query = { ...DEFAULT_LIBRARY_QUERY, is_favorite: false };
    expect(libraryQuerySearchString(query)).toBe("?is_favorite=false");
    expect(isDefaultLibraryQuery(query)).toBe(false);
  });

  it("emits keys in a fixed order so the same view is the same URL", () => {
    const query: LibraryQuery = {
      ...DEFAULT_LIBRARY_QUERY,
      search: "solo",
      sort: "title",
      is_favorite: true,
    };
    expect(libraryQuerySearchString(query)).toBe(
      "?search=solo&sort=title&is_favorite=true",
    );
  });
});

describe("round trip", () => {
  const cases: Array<[string, LibraryQuery]> = [
    ["default", DEFAULT_LIBRARY_QUERY],
    ["search only", { ...DEFAULT_LIBRARY_QUERY, search: "tower of god" }],
    ["sort only", { ...DEFAULT_LIBRARY_QUERY, sort: "title" }],
    ["favourites on", { ...DEFAULT_LIBRARY_QUERY, is_favorite: true }],
    [
      "everything at once",
      {
        search: "a b",
        sort: "created_at",
        status: "unread",
        reading_status: "reading",
        is_favorite: true,
      },
    ],
  ];

  for (const [name, query] of cases) {
    it(`survives serialize → parse: ${name}`, () => {
      expect(roundTrip(query)).toEqual(query);
    });
  }
});

describe("hasActiveFilters", () => {
  it("ignores the search term, which has its own empty state", () => {
    expect(hasActiveFilters({ ...DEFAULT_LIBRARY_QUERY, search: "solo" })).toBe(false);
  });

  it("notices any narrowing filter", () => {
    expect(hasActiveFilters({ ...DEFAULT_LIBRARY_QUERY, is_favorite: true })).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_LIBRARY_QUERY, status: "unread" })).toBe(true);
    expect(
      hasActiveFilters({ ...DEFAULT_LIBRARY_QUERY, reading_status: "reading" }),
    ).toBe(true);
  });
});

describe("libraryQueryToListParams", () => {
  it("sends nulls as absent rather than as literal nulls", () => {
    expect(
      libraryQueryToListParams(DEFAULT_LIBRARY_QUERY, { page: 1, per_page: 200 }),
    ).toEqual({
      page: 1,
      per_page: 200,
      sort: DEFAULT_LIBRARY_QUERY.sort,
      search: undefined,
      status: undefined,
      reading_status: undefined,
      is_favorite: undefined,
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
