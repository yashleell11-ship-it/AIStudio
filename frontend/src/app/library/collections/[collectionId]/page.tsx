import { CollectionDetailView } from "@/features/library";

interface CollectionPageProps {
  params: Promise<{ collectionId: string }>;
}

export default async function CollectionPage({ params }: CollectionPageProps) {
  const { collectionId } = await params;
  return <CollectionDetailView collectionId={Number(collectionId)} />;
}
