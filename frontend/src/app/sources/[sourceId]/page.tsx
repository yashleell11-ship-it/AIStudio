import { SourceBrowserView } from "@/features/sources";

interface SourcePageProps {
  params: Promise<{ sourceId: string }>;
}

export default async function SourcePage({ params }: SourcePageProps) {
  const { sourceId } = await params;
  return <SourceBrowserView sourceId={sourceId} />;
}
