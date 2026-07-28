import { SourceSeriesDetailView } from "@/features/sources";
import { decodeRouteParam } from "@/lib/route-params";

interface SourceSeriesPageProps {
  params: Promise<{ sourceId: string; seriesId: string }>;
}

export default async function SourceSeriesPage({ params }: SourceSeriesPageProps) {
  const { sourceId, seriesId } = await params;

  return (
    <SourceSeriesDetailView
      sourceId={decodeRouteParam(sourceId)}
      seriesId={decodeRouteParam(seriesId)}
    />
  );
}
