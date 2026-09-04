import { NovelReader } from "@/features/novels";
import { decodeRouteParam } from "@/lib/route-params";

interface NovelReaderPageProps {
  params: Promise<{
    sourceId: string;
    seriesKey: string;
    /** Catch-all: opaque chapter keys routinely contain `/`. */
    chapterKey: string[];
  }>;
  /** `page` is the progress BUCKET, the same param the manga reader uses. */
  searchParams: Promise<{ page?: string }>;
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
  const { page } = await searchParams;
  const initialPage = page ? Number(page) : 1;

  return (
    <NovelReader
      key={`${sourceId}:${seriesKey}:${chapterKey}`}
      sourceId={sourceId}
      seriesKey={seriesKey}
      chapterKey={chapterKey}
      initialPage={Number.isFinite(initialPage) ? initialPage : 1}
    />
  );
}
