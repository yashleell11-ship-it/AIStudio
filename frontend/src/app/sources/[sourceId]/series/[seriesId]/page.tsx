import { SourceSeriesDetailView } from "@/features/sources";

interface SourceSeriesPageProps {
  params: Promise<{ sourceId: string; seriesId: string }>;
}

export default async function SourceSeriesPage({ params }: SourceSeriesPageProps) {
  const { sourceId, seriesId } = await params;

  return <SourceSeriesDetailView sourceId={sourceId} seriesId={seriesId} />;
}
