import { ReadAllReader } from "@/features/reader";
import { decodeRouteParam } from "@/lib/route-params";

interface ReadAllPageProps {
  params: Promise<{ sourceId: string; seriesKey: string }>;
  /** `from` names the chapter to resume at; `page` its page within it. */
  searchParams: Promise<{ from?: string; page?: string }>;
}

/**
 * The whole series, as one scroll (spec 2026-09-05 R2).
 *
 * A route of its own rather than a mode on the chapter reader: that route ends
 * in an opaque catch-all chapter key, so any marker segment could equally be a
 * real chapter. The resume point travels as a query parameter for the usual
 * reason — connector chapter keys contain slashes.
 */
export default async function ReadAllPage({ params, searchParams }: ReadAllPageProps) {
  const { sourceId: rawSource, seriesKey: rawSeries } = await params;
  const sourceId = decodeRouteParam(rawSource);
  const seriesKey = decodeRouteParam(rawSeries);
  const { from, page } = await searchParams;
  const initialPage = page ? Number(page) : 1;

  return (
    <ReadAllReader
      key={`${sourceId}:${seriesKey}`}
      sourceId={sourceId}
      seriesKey={seriesKey}
      fromChapterKey={from ?? null}
      initialPage={Number.isFinite(initialPage) ? initialPage : 1}
    />
  );
}
