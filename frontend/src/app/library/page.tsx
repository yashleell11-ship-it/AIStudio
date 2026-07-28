import { Suspense } from "react";
import { LibraryView } from "@/features/library";

export default function LibraryPage() {
  return (
    // The view's filters and sort live in the query string, and `useSearchParams`
    // has to sit under a Suspense boundary or it opts the whole route out of
    // static rendering.
    <Suspense fallback={<div className="p-6 text-muted">Loading library…</div>}>
      <LibraryView />
    </Suspense>
  );
}
