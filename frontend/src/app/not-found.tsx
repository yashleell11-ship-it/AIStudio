import type { Metadata } from "next";
import { GhostPillButton } from "@/components/premium/GhostPillButton";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { StatusScreen } from "@/components/layout/status-screen";
import { Kbd } from "@/components/ui/kbd";

export const metadata: Metadata = {
  title: "Not found — ManhwaManiacs",
};

/**
 * Catch-all 404. Renders inside the app shell, so the sidebar, topbar and the
 * active profile's mood tint stay put — a mistyped URL should feel like a wrong
 * turn inside the app, not like leaving it.
 */
export default function NotFound() {
  return (
    <StatusScreen
      code="404"
      title="Nothing here"
      description={
        <>
          This page does not exist. It may have been renamed, or the series it
          pointed at may have been removed from your library.
        </>
      }
      actions={
        <>
          <PrimaryPillButton href="/" label="Back home" />
          <GhostPillButton href="/library" label="Open library" />
        </>
      }
      footnote={
        <span className="inline-flex flex-wrap items-center justify-center gap-1.5">
          Looking for something specific? Press <Kbd>Ctrl</Kbd>
          <Kbd>K</Kbd> to search everything.
        </span>
      }
    />
  );
}
