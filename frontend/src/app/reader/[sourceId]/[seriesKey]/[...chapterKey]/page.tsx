import { SourceReader } from "@/features/reader";
import { decodeRouteParam } from "@/lib/route-params";

interface ReaderPageProps {
  params: Promise<{
    sourceId: string;
    seriesKey: string;
    /** Catch-all: opaque chapter keys routinely contain `/`. */
    chapterKey: string[];
  }>;
  searchParams: Promise<{ page?: string }>;
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
  const { page } = await searchParams;
  const initialPage = page ? Number(page) : 1;

  return (
    <SourceReader
      key={`${sourceId}:${seriesKey}:${chapterKey}`}
      sourceId={sourceId}
      seriesKey={seriesKey}
      chapterKey={chapterKey}
      initialPage={Number.isFinite(initialPage) ? initialPage : 1}
    />
  );
}
