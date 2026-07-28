"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  type LibraryQuery,
  libraryQuerySearchString,
  parseLibraryQuery,
} from "./url-state";

export interface LibraryUrlState {
  query: LibraryQuery;
  /**
   * Write a view state to the URL.
   *
   * `replace` for anything that changes on every keystroke — a pushed entry per
   * character turns the back button into a character-by-character rewind.
   * Discrete controls (sort, a chip, a select) push, so back genuinely undoes
   * the last thing the user clicked.
   */
  setQuery: (next: LibraryQuery, options?: { replace?: boolean }) => void;
}

/**
 * The library's filter/sort state, with the query string as the single source of
 * truth rather than a mirror of component state.
 *
 * Holding it in `useState` and merely reflecting it into the URL is the version
 * that breaks: the back button would then move history without moving the grid.
 * Reading from `useSearchParams` means a refresh, a bookmark, a shared link and
 * the back button all arrive at the same view for the same reason.
 */
export function useLibraryUrlState(): LibraryUrlState {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Depend on the serialized string, not the params object: Next hands back a
  // new instance on every render, which would re-parse (and re-run every
  // dependent query) forever.
  const serialized = searchParams.toString();
  const query = useMemo(
    () => parseLibraryQuery(new URLSearchParams(serialized)),
    [serialized],
  );

  const setQuery = useCallback(
    (next: LibraryQuery, options?: { replace?: boolean }) => {
      const url = `${pathname}${libraryQuerySearchString(next)}`;
      // `scroll: false`: changing a filter should leave the reader where they
      // are in the grid, not jump them to the top of the page.
      if (options?.replace) {
        router.replace(url, { scroll: false });
      } else {
        router.push(url, { scroll: false });
      }
    },
    [pathname, router],
  );

  return { query, setQuery };
}
