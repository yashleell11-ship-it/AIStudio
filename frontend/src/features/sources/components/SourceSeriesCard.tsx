"use client";

import Image from "next/image";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { GRID_ITEM_ATTRIBUTE } from "@/lib/keyboard";
import { sourceImageUrl } from "../api";
import type { SourceSeriesSummary } from "../types";

/**
 * The catalog grid's cell. `SourceSeriesGrid` is `grid-cols-2 gap-4` inside the
 * view's `p-6`, which is `calc(50vw - 32px)` — 155px on a 375px phone, the box
 * the 1.6 MB covers were being painted into. Above `sm` the grid climbs to six
 * columns, so the wide branch names the widest cell rather than tracking each
 * breakpoint: over-asking on a desktop costs one rung of the server's ladder,
 * under-asking is a blurry catalog.
 *
 * This is both the browser's `sizes` hint and the width the cover proxy renders
 * to — see `lib/cover-url.ts`.
 */
const COVER_SIZES = "(max-width: 639px) calc(50vw - 32px), 260px";

interface SourceSeriesCardProps {
  sourceId: string;
  series: SourceSeriesSummary;
}

export function SourceSeriesCard({ sourceId, series }: SourceSeriesCardProps) {
  return (
    <Link
      href={`/sources/${sourceId}/series/${encodeURIComponent(series.id)}`}
      // Cell of the keyboard-navigable catalog grid; the ring is what makes
      // arrow-key movement legible.
      {...{ [GRID_ITEM_ATTRIBUTE]: "" }}
      className="block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
    >
      <Card className="group overflow-hidden border-transparent bg-transparent shadow-none transition-colors">
        <div className="relative aspect-[2/3] w-full overflow-hidden rounded-2xl border border-border bg-surface-2 transition duration-200 group-hover:border-primary/40 group-hover:ring-2 group-hover:ring-primary/20">
          <Image
            src={sourceImageUrl(series.cover_url, COVER_SIZES)}
            alt={series.title}
            fill
            className="object-cover transition-transform duration-200 group-hover:scale-105"
            sizes={COVER_SIZES}
            unoptimized
          />
        </div>
        <p className="mt-2 line-clamp-2 px-0.5 text-sm font-medium leading-snug text-fg">
          {series.title}
        </p>
      </Card>
    </Link>
  );
}
