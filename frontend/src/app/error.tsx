"use client";

import { useEffect } from "react";
import { GhostPillButton } from "@/components/premium/GhostPillButton";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { StatusScreen } from "@/components/layout/status-screen";
import { ApiError } from "@/types/api";

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * What a viewer sees when a route throws during render.
 *
 * `reset()` re-renders the segment without a full page load, so a transient
 * failure (a request that timed out, a source that blinked) costs one click
 * rather than a reload that also drops every warm cache.
 */
export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    // Next.js only forwards the digest to the client in production; the message
    // stays server-side. Logging here is what makes the browser console useful
    // when someone reports "it just broke".
    console.error("Route error:", error);
  }, [error]);

  // A dead backend is by far the most common cause and has a different answer
  // than a genuine bug, so it gets its own copy rather than "Something broke".
  const offline = error instanceof ApiError && error.status === 0;

  return (
    <StatusScreen
      code={offline ? "···" : "500"}
      title={offline ? "Can't reach the server" : "Something broke"}
      description={
        offline ? (
          <>
            The ManhwaManiacs backend did not answer. It may still be starting
            up, or the connection dropped. Your library is untouched.
          </>
        ) : (
          <>
            This page failed while rendering. Nothing was lost — trying again is
            usually enough.
          </>
        )
      }
      actions={
        <>
          <PrimaryPillButton onClick={reset} label="Try again" />
          <GhostPillButton href="/" label="Back home" />
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
  );
}
