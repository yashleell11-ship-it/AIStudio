import { parseUtcTimestamp } from "@/lib/utc-time";
import type { SourceChapterProgress, SourceSeriesProgressMap } from "./source-progress";

/**
 * Where a profile is in each chapter of one series, for the series page's
 * chapter list and its Continue button.
 *
 * The source-native rewrite moved reading position to the server
 * (`POST /reader/progress`, read back with `GET /reader/progress/series`) and
 * dropped the reader's write to the client-side `mm.source-progress` store —
 * but the series page kept reading only that store, which now nothing writes.
 * The result was a series page that never showed a read chapter and a Continue
 * button that never appeared, however much of the series had been read.
 *
 * Server rows are therefore the source of truth here. The local store is still
 * merged UNDER them so the positions adopted from a pre-scoping device (see
 * `adoptLegacySourceProgress`) stay visible for chapters the server has never
 * been told about; it can never override a server row.
 */

/** One stored position, as `GET /reader/progress/series` serialises it. */
export interface ServerChapterProgress {
  chapter_key: string;
  last_page: number;
  page_count: number;
  is_completed: boolean;
  last_read_at: string | null;
}

/** Server rows keyed by chapter key, in the shape the chapter list renders. */
export function serverProgressMap(
  rows: readonly ServerChapterProgress[],
): SourceSeriesProgressMap {
  const map: SourceSeriesProgressMap = {};
  for (const row of rows) {
    if (!row.chapter_key) continue;
    map[row.chapter_key] = {
      page: Math.max(1, Math.round(row.last_page)),
      pageCount: Math.max(0, Math.round(row.page_count)),
      completed: Boolean(row.is_completed),
      updatedAt: row.last_read_at ?? "",
    };
  }
  return map;
}

/** Server wins per chapter; local records fill only the gaps. */
export function mergeSeriesProgress(
  local: SourceSeriesProgressMap,
  server: SourceSeriesProgressMap,
): SourceSeriesProgressMap {
  return { ...local, ...server };
}

/**
 * The most recently read chapter, or null.
 *
 * Compared through `parseUtcTimestamp` rather than as strings: server rows
 * carry a naive-UTC `last_read_at` while local records carry a `Z`-suffixed
 * ISO string, so a lexicographic compare would rank the two formats against
 * each other by their text, not their instant.
 */
export function pickLatestProgress(
  map: SourceSeriesProgressMap,
): { chapterId: string; progress: SourceChapterProgress } | null {
  let latest: { chapterId: string; progress: SourceChapterProgress } | null = null;
  let latestMs = Number.NEGATIVE_INFINITY;
  for (const [chapterId, progress] of Object.entries(map)) {
    const at = parseUtcTimestamp(progress.updatedAt) ?? Number.NEGATIVE_INFINITY;
    if (latest === null || at > latestMs) {
      latest = { chapterId, progress };
      latestMs = at;
    }
  }
  return latest;
}

export interface SeriesProgressInput {
  /** Rows from `GET /reader/progress/series`; empty while it loads. */
  serverRows: readonly ServerChapterProgress[];
  /** The device's own `mm.source-progress` records for this series. */
  localMap: SourceSeriesProgressMap;
}

export interface SeriesProgressView {
  map: SourceSeriesProgressMap;
  latest: { chapterId: string; progress: SourceChapterProgress } | null;
}

/** Everything the series page needs to render progress, from both stores. */
export function resolveSeriesProgress({
  serverRows,
  localMap,
}: SeriesProgressInput): SeriesProgressView {
  const map = mergeSeriesProgress(localMap, serverProgressMap(serverRows));
  return { map, latest: pickLatestProgress(map) };
}
