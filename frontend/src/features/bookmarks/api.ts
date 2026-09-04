import { http } from "@/services/http";
import type { SeriesId } from "@/types/api";
import type { Bookmark, BookmarkCreate } from "./types";

/**
 * The three bookmark endpoints, in one place.
 *
 * They used to be two: `readerApi.addBookmark` posted the create and
 * `libraryApi.listBookmarks` / `deleteBookmark` did the reads — so the wire
 * shape was described twice and only one copy was ever updated. The endpoints
 * are all under `/reader/` because that is where the backend router puts them;
 * the client grouping follows the feature, not the URL prefix.
 *
 * The offline-sync batch (`POST /reader/bookmarks/batch`) is deliberately
 * absent: it exists for a device with a create/delete OUTBOX to flush, which
 * the web does not have and is not getting. The browser's offline story is the
 * service worker caching the LISTING so saved places can be read with no
 * signal (see the `/reader/bookmarks` entry in `public/sw-policy.js`); the
 * phone stays the offline-first client that can also capture while
 * disconnected.
 */
export const bookmarksApi = {
  /** One deliberate capture. Returns the stored row, `client_id` included. */
  create: (body: BookmarkCreate) => http.post<Bookmark>("/reader/bookmark", body),

  list: (ref?: Partial<SeriesId>) =>
    http.get<Bookmark[]>("/reader/bookmarks", {
      query: { source: ref?.sourceId, series: ref?.seriesKey },
    }),

  /** Tombstones the row; the server never removes it. */
  remove: (bookmarkId: number) => http.delete<void>(`/reader/bookmarks/${bookmarkId}`),
};
