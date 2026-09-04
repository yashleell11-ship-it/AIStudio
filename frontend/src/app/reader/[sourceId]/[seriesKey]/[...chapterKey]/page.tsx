import { SourceReader } from "@/features/reader";
import { parseAnchorParams } from "@/features/bookmarks";
import { decodeRouteParam } from "@/lib/route-params";

interface ReaderPageProps {
  params: Promise<{
    sourceId: string;
    seriesKey: string;
    /** Catch-all: opaque chapter keys routinely contain `/`. */
    chapterKey: string[];
  }>;
  /**
   * `page` is the page to open on; `at` is how far DOWN that page, which only
   * a bookmark link carries (`features/bookmarks/anchor.ts`). Without `at` the
   * reader keeps its long-standing "top of that page" behaviour.
   */
  searchParams: Promise<{ page?: string; at?: string }>;
}

export default async function ReaderChapterPage({
  params,
  searchParams,
}: ReaderPageProps) {
  const { sourceId: rawSource, seriesKey: rawSeries, chapterKey: rawChapter } =
    await params;
  const sourceId = decodeRouteParam(rawSource);
  const seriesKey = decodeRouteParam(rawSeries);
  const chapterKey = rawChapter.map(decodeRouteParam).join("/");
  const { page, at } = await searchParams;
  const initialPage = page ? Number(page) : 1;
  const anchor = parseAnchorParams(page, at);

  return (
    <SourceReader
      key={`${sourceId}:${seriesKey}:${chapterKey}`}
      sourceId={sourceId}
      seriesKey={seriesKey}
      chapterKey={chapterKey}
      initialPage={Number.isFinite(initialPage) ? initialPage : 1}
      initialAnchorFraction={at != null && anchor ? anchor.fraction : null}
    />
  );
}
