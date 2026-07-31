import { Suspense } from "react";
import { LibraryView } from "@/features/library";

/**
 * The full, filterable catalogue — everything on this server, not just what
 * this profile follows. Mirrors `/library/browse` on mobile.
 */
export default function LibraryBrowsePage() {
  return (
    // The view's filters and sort live in the query string, and `useSearchParams`
    // has to sit under a Suspense boundary or it opts the whole route out of
    // static rendering.
    <Suspense fallback={<div className="p-6 text-muted">Loading library…</div>}>
      <LibraryView />
    </Suspense>
  );
}
