import { BasicReader } from "@/features/reader";

interface ReaderPageProps {
  params: Promise<{ seriesId: string; chapterId: string }>;
  searchParams: Promise<{ page?: string }>;
}

export default async function ReaderChapterPage({
  params,
  searchParams,
}: ReaderPageProps) {
  const { seriesId, chapterId } = await params;
  const { page } = await searchParams;
  const parsedSeriesId = Number(seriesId);
  const parsedChapterId = Number(chapterId);
  const initialPage = page ? Number(page) : 1;

  return (
    <BasicReader
      key={`${parsedSeriesId}-${parsedChapterId}`}
      seriesId={parsedSeriesId}
      chapterId={parsedChapterId}
      initialPage={Number.isFinite(initialPage) ? initialPage : 1}
    />
  );
}
