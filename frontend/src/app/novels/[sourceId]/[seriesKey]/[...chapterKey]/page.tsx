import { NovelReader } from "@/features/novels";
import { parseAnchorParams } from "@/features/bookmarks";
import { decodeRouteParam } from "@/lib/route-params";

interface NovelReaderPageProps {
  params: Promise<{
    sourceId: string;
    seriesKey: string;
    /** Catch-all: opaque chapter keys routinely contain `/`. */
    chapterKey: string[];
  }>;
  /**
   * `page` is the progress BUCKET, the same param the manga reader uses.
   * `para` + `at` are a BOOKMARK's exact spot — a paragraph index and a
   * fraction within it — which is a different thing from a bucket and so gets
   * a parameter of its own (`features/bookmarks/anchor.ts`).
   */
  searchParams: Promise<{ page?: string; para?: string; at?: string }>;
}

export default async function NovelChapterPage({
  params,
  searchParams,
}: NovelReaderPageProps) {
  const { sourceId: rawSource, seriesKey: rawSeries, chapterKey: rawChapter } =
    await params;
  const sourceId = decodeRouteParam(rawSource);
  const seriesKey = decodeRouteParam(rawSeries);
  const chapterKey = rawChapter.map(decodeRouteParam).join("/");
  const { page, para, at } = await searchParams;
  const initialPage = page ? Number(page) : 1;
  const anchor = parseAnchorParams(para, at);

  return (
    <NovelReader
      key={`${sourceId}:${seriesKey}:${chapterKey}`}
      sourceId={sourceId}
      seriesKey={seriesKey}
      chapterKey={chapterKey}
      initialPage={Number.isFinite(initialPage) ? initialPage : 1}
      initialParagraph={anchor?.index ?? null}
      initialAnchorFraction={anchor?.fraction ?? null}
    />
  );
}
