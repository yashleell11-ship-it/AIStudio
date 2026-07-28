import { Suspense } from "react";
import { decodeRouteParam } from "@/lib/route-params";
import { SourceBrowserView } from "@/features/sources";

interface SourcePageProps {
  params: Promise<{ sourceId: string }>;
}

export default async function SourcePage({ params }: SourcePageProps) {
  const { sourceId: rawSourceId } = await params;
  const sourceId = decodeRouteParam(rawSourceId);
  return (
    <Suspense fallback={<div className="p-6 text-muted">Loading source…</div>}>
      <SourceBrowserView sourceId={sourceId} />
    </Suspense>
  );
}
