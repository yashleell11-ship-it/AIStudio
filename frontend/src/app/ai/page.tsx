import { Sparkles } from "lucide-react";
import { PagePlaceholder } from "@/components/layout/page-placeholder";

export default function AiPage() {
  return (
    <PagePlaceholder
      title="AI"
      description="Chat, summaries, OCR, and enhancement powered by your local models."
      icon={Sparkles}
    />
  );
}
