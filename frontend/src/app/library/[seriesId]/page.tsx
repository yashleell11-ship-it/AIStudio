import { SeriesDetailView } from "@/features/library/components/SeriesDetailView";

interface SeriesPageProps {
  params: Promise<{ seriesId: string }>;
}

export default async function SeriesPage({ params }: SeriesPageProps) {
  const { seriesId } = await params;
  return <SeriesDetailView seriesId={Number(seriesId)} />;
}
