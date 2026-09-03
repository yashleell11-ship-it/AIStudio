import type { Metadata } from "next";
import { DownloadsView } from "@/features/offline";

export const metadata: Metadata = {
  title: "Downloads · ManhwaManiacs",
  description: "Chapters saved on this device, and what they cost in storage.",
};

export default function DownloadsPage() {
  return <DownloadsView />;
}
