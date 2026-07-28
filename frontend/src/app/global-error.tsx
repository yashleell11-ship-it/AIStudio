"use client";

import { useEffect } from "react";
import { GhostPillButton } from "@/components/premium/GhostPillButton";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { StatusScreen } from "@/components/layout/status-screen";
import "./globals.css";

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Last resort: the ROOT LAYOUT itself threw, so `app/error.tsx` never got to
 * render and this replaces the whole document — which is why it emits its own
 * `<html>`/`<body>`.
 *
 * It styles itself from `globals.css` (so it is still Eclipse Warm) but does
 * NOT load the web fonts or mount any provider: at this point the thing that
 * broke may be exactly one of those, and a fallback that depends on the failure
 * is not a fallback. Recovery is a real navigation rather than a client-side
 * one for the same reason.
 */
export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    console.error("Root layout error:", error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <main className="flex min-h-dvh items-center justify-center bg-bg text-fg">
          <StatusScreen
            code="500"
            title="ManhwaManiacs failed to start"
            description={
              <>
                The application shell could not render. Reloading usually clears
                it; if it does not, the backend or the running build is the place
                to look.
              </>
            }
            actions={
              <>
                <PrimaryPillButton onClick={reset} label="Try again" />
                <GhostPillButton
                  onClick={() => window.location.assign("/")}
                  label="Reload the app"
                />
              </>
            }
            footnote={
              error.digest ? (
                <>
                  Reference{" "}
                  <code className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-fg">
                    {error.digest}
                  </code>
                </>
              ) : null
            }
          />
        </main>
      </body>
    </html>
  );
}
