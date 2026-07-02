import { SourceReader } from "@/features/reader";

interface OnlineReaderPageProps {
  params: Promise<{ sourceId: string; seriesId: string; chapterId: string }>;
  searchParams: Promise<{ page?: string }>;
}

export default async function OnlineReaderPage({
  params,
  searchParams,
}: OnlineReaderPageProps) {
  const { sourceId, seriesId, chapterId } = await params;
  const { page } = await searchParams;
  const initialPage = page ? Number(page) : 1;

  return (
    <SourceReader
      key={`${sourceId}-${seriesId}-${chapterId}`}
      sourceId={sourceId}
      seriesId={seriesId}
      chapterId={chapterId}
      initialPage={Number.isFinite(initialPage) ? initialPage : 1}
    />
  );
}
