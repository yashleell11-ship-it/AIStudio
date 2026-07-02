import type { SourceSeriesSummary } from "./types";

/** Merge paginated series lists without duplicate ids (first occurrence wins). */
export function dedupeSeriesItems(items: SourceSeriesSummary[]): SourceSeriesSummary[] {
  const seen = new Set<string>();
  const result: SourceSeriesSummary[] = [];
  for (const item of items) {
    if (seen.has(item.id)) {
      continue;
    }
    seen.add(item.id);
    result.push(item);
  }
  return result;
}
