import { BookOpen } from "lucide-react";
import { PagePlaceholder } from "@/components/layout/page-placeholder";

export default function ReaderLandingPage() {
  return (
    <PagePlaceholder
      title="Reader"
      description="Open a series from your library to start reading."
      icon={BookOpen}
      actionHref="/library"
      actionLabel="Go to library"
    />
  );
}
