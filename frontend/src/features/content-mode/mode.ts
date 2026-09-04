import type { SourceSummary } from "@/features/sources/types";

/**
 * Content mode — the app-wide Manga / Novels switch.
 *
 * Novels are not a second kind of row inside the manga app: they are a
 * different reading life with a different library, and mixing a 61k-title
 * novel archive into a sources list of manhwa sites makes both harder to use.
 * So the mode scopes EVERY list that could hold either kind (library, browse,
 * sources, search, updates, downloads, collections, recommendations, history,
 * bookmarks), the same way a profile scopes them.
 *
 * Two invariants this module exists to hold:
 *
 * 1. **Manga mode is today's app, exactly.** The manga predicate is "not a
 *    novel", never "is a manga" — so a connector that omits `content_kind`, or
 *    a deployment with `MM_NOVELS_ENABLED` off (where the registry hides novel
 *    sources entirely and nothing is ever tagged `"novel"`), filters to the
 *    identical list it renders today. The filter is a no-op, not a rewrite.
 *
 * 2. **Flag off means no mode at all.** With novels disabled the switch does
 *    not render and the effective mode is forced to manga regardless of what
 *    is stored — a profile that used Novels mode while the flag was on cannot
 *    come back to a half-empty app after it is turned off again.
 */

export const CONTENT_MODES = ["manga", "novel"] as const;

export type ContentMode = (typeof CONTENT_MODES)[number];

/** What the owner reads daily, and what every existing library row is. */
export const DEFAULT_CONTENT_MODE: ContentMode = "manga";

export function isContentMode(value: unknown): value is ContentMode {
  return (
    typeof value === "string" && (CONTENT_MODES as readonly string[]).includes(value)
  );
}

/** A stored preference, or `null` when there is none to honour. */
export function parseContentMode(raw: string | null): ContentMode | null {
  if (raw === null) return null;
  return isContentMode(raw.trim()) ? (raw.trim() as ContentMode) : null;
}

/**
 * The mode actually in force.
 *
 * `novelsEnabled` is the production gate (`/auth/bootstrap-status`): with it
 * off there is exactly one mode and it is manga, whatever localStorage says.
 */
export function resolveContentMode(
  stored: ContentMode | null,
  novelsEnabled: boolean,
): ContentMode {
  if (!novelsEnabled) return DEFAULT_CONTENT_MODE;
  return stored ?? DEFAULT_CONTENT_MODE;
}

/** The kind a source serves. Anything unlabelled is manga — see invariant 1. */
export function sourceContentMode(
  source: Pick<SourceSummary, "content_kind"> | null | undefined,
): ContentMode {
  return source?.content_kind === "novel" ? "novel" : "manga";
}

/**
 * `source_id -> mode` for every installed source, built once from
 * `GET /sources`. Rows elsewhere in the app (follows, notifications, history,
 * bookmarks) carry a source id but not a kind, so this index is how they get
 * scoped without a backend change or a new column.
 */
export function buildSourceModeIndex(
  sources: readonly SourceSummary[] | undefined,
): Map<string, ContentMode> {
  const index = new Map<string, ContentMode>();
  for (const source of sources ?? []) {
    index.set(source.id, sourceContentMode(source));
  }
  return index;
}

/**
 * Whether a row from `sourceId` belongs in `mode`.
 *
 * An UNKNOWN source id — one the listing does not carry, because the connector
 * was removed, is hidden by the 18+ gate, or the list has not loaded yet —
 * resolves to manga, so it keeps showing exactly where it shows today and a
 * slow `/sources` response cannot blank the library. The cost is that an
 * orphaned novel follow would appear in manga mode; the alternative (hiding
 * unknown rows) would flash the whole library empty on every cold load.
 */
export function matchesContentMode(
  sourceId: string | null | undefined,
  index: ReadonlyMap<string, ContentMode>,
  mode: ContentMode,
): boolean {
  if (sourceId == null) return mode === "manga";
  return (index.get(sourceId) ?? "manga") === mode;
}

/** Keep the rows of `mode`, reading each row's source id with `getSourceId`. */
export function filterByContentMode<T>(
  rows: readonly T[],
  index: ReadonlyMap<string, ContentMode>,
  mode: ContentMode,
  getSourceId: (row: T) => string | null | undefined,
): T[] {
  return rows.filter((row) => matchesContentMode(getSourceId(row), index, mode));
}

/**
 * Keep the sources of `mode`, straight off `content_kind` — no index needed,
 * this IS the index's input.
 */
export function filterSourcesByContentMode(
  sources: readonly SourceSummary[],
  mode: ContentMode,
): SourceSummary[] {
  return sources.filter((source) => sourceContentMode(source) === mode);
}

export interface ContentModeCopy {
  /** The switch's own label. */
  label: string;
  /** Used in empty states: "No novels in your library yet". */
  plural: string;
}

export const CONTENT_MODE_COPY: Record<ContentMode, ContentModeCopy> = {
  manga: { label: "Manga", plural: "series" },
  novel: { label: "Novels", plural: "novels" },
};
