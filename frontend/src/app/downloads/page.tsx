import type { Metadata } from "next";
import { OfflineLibraryView } from "@/features/offline";

export const metadata: Metadata = {
  title: "Offline · ManhwaManiacs",
  description: "Chapters saved on this device, and what they cost in storage.",
};

export default function OfflinePage() {
  return <OfflineLibraryView />;
}
