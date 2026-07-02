import { PenTool } from "lucide-react";
import { PagePlaceholder } from "@/components/layout/page-placeholder";

export default function CreatePage() {
  return (
    <PagePlaceholder
      title="Create"
      description="The manhwa creation studio: characters, world, panels, and image generation."
      icon={PenTool}
    />
  );
}
