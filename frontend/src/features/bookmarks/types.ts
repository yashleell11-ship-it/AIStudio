/**
 * Bookmarks on the wire.
 *
 * A bookmark is neither a reader thing nor a library thing — it is captured in
 * a reader and listed in the library — so it lives in its own feature rather
 * than being half-owned by each. Before this module the type was declared
 * twice (`features/reader/api.ts` and `features/library/types.ts`) and the
 * three endpoints were split across two api files; both copies described a
 * bookmark as `{page, note}`, which is not what the server stores any more.
 *
 * The position is the backend's generic anchor triple plus a `media_type`
 * discriminator (see `backend/database/models.py::Bookmark` and
 * `backend/services/bookmark_service.py`): `anchor_index` counts PAGES for
 * manga and PARAGRAPHS for novels, 1-based in both; `anchor_fraction` is
 * 0.0–1.0 *within* that unit; `anchor_total` is the unit count the capturing
 * client saw, with 0 meaning "unknown" (rows migrated from the page-only
 * schema).
 */

/** What `anchor_index` counts. */
export type BookmarkMediaType = "manga" | "novel";

export const BOOKMARK_MEDIA_MANGA = "manga";
export const BOOKMARK_MEDIA_NOVEL = "novel";

/**
 * A position inside one chapter, in whichever unit its medium counts in.
 *
 * The client-side mirror of the stored triple. Kept as its own type — rather
 * than passing three loose numbers — because every operation over it (the
 * fraction-of-chapter maths, the clamp-to-nearest-valid degradation, the URL
 * round trip) applies to all three together, and a `total` that has drifted
 * away from its `index` is the bug this feature exists to avoid.
 */
export interface BookmarkAnchor {
  mediaType: BookmarkMediaType;
  /** 1-based page (manga) or paragraph (novel). */
  index: number;
  /** 0.0–1.0 within that unit. */
  fraction: number;
  /** Units in the chapter when this was captured. 0 = unknown. */
  total: number;
}

/** One bookmark, exactly as `bookmark_service._serialize` emits it. */
export interface Bookmark {
  id: number;
  /** Client-generated sync identity. Opaque — never parsed. */
  client_id: string;
  source_id: string;
  series_key: string;
  /** Off the followed-series row; null when the series is not followed. */
  series_title: string | null;
  chapter_key: string;
  chapter_number: number | null;
  media_type: string;
  anchor_index: number;
  anchor_fraction: number;
  anchor_total: number;
  /**
   * Deprecated mirror of `anchor_index` for manga, null for novels. Kept on
   * the type because the server still sends it; nothing here reads it.
   */
  page: number | null;
  /** 0.0–1.0 through the chapter, or null when `anchor_total` is 0. */
  position_fraction: number | null;
  /** The cached sanitized text at that point. Novels with cached text only. */
  snippet: string | null;
  /** The recorded paragraph no longer exists; the nearest valid one was used. */
  anchor_stale: boolean;
  note: string | null;
  deleted: boolean;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
}

/** The body of `POST /reader/bookmark` — one deliberate capture. */
export interface BookmarkCreate {
  source_id: string;
  series_key: string;
  chapter_key: string;
  chapter_number?: number | null;
  media_type: BookmarkMediaType;
  anchor_index: number;
  anchor_fraction: number;
  anchor_total: number;
  note?: string | null;
}
