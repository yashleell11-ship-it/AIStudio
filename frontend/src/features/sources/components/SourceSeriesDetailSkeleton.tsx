import { Card, CardContent, CardHeader } from "@/components/ui/card";

/**
 * The shape of a source's series page, drawn before its data lands.
 *
 * Every cover in Browse leads here, and this screen used to answer with the
 * words "Loading series…" centred in an empty viewport — the layout then
 * appeared all at once and pushed nothing where the eye already was. The
 * skeleton mirrors the real grid (`220px` sticky cover column, title, meta,
 * actions, chapter rows) so the page does not move when the data arrives.
 */
export function SourceSeriesDetailSkeleton() {
  return (
    <div className="p-6" aria-busy="true" aria-label="Loading series">
      <div className="mb-6 h-5 w-32 animate-pulse rounded bg-surface-2" />

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <Card className="overflow-hidden rounded-3xl lg:sticky lg:top-24 lg:self-start">
          <div className="aspect-[2/3] w-full animate-pulse bg-surface-2" />
        </Card>

        <div>
          <div className="h-10 w-2/3 animate-pulse rounded bg-surface-2" />
          <div className="mt-3 h-4 w-40 animate-pulse rounded bg-surface-2" />
          <div className="mt-2 h-4 w-32 animate-pulse rounded bg-surface-2" />
          <div className="mt-3 flex flex-wrap gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="h-6 w-20 animate-pulse rounded-full bg-surface-2" />
            ))}
          </div>
          <div className="mt-4 space-y-2">
            <div className="h-4 w-full max-w-3xl animate-pulse rounded bg-surface-2" />
            <div className="h-4 w-full max-w-3xl animate-pulse rounded bg-surface-2" />
            <div className="h-4 w-2/3 max-w-3xl animate-pulse rounded bg-surface-2" />
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            <div className="h-11 w-36 animate-pulse rounded-full bg-surface-2" />
            <div className="h-10 w-24 animate-pulse rounded-lg bg-surface-2" />
          </div>
        </div>
      </div>

      <Card className="mt-8">
        <CardHeader>
          <div className="h-6 w-28 animate-pulse rounded bg-surface-2" />
        </CardHeader>
        <CardContent>
          <ChapterRowsSkeleton />
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Chapter rows alone — the chapters request resolves separately from the series
 * summary, so the list keeps its own placeholder after the header has painted.
 */
export function ChapterRowsSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="divide-y divide-border" aria-busy="true" aria-label="Loading chapters">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="flex items-center justify-between gap-3 px-2 py-3 first:pt-0"
        >
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-4 w-40 animate-pulse rounded bg-surface-2" />
            <div className="h-3 w-24 animate-pulse rounded bg-surface-2" />
          </div>
          <div className="h-8 w-16 animate-pulse rounded-lg bg-surface-2" />
        </div>
      ))}
    </div>
  );
}
