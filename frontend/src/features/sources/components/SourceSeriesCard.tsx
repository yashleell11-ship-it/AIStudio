"use client";

import Image from "next/image";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { GRID_ITEM_ATTRIBUTE } from "@/lib/keyboard";
import { sourceImageUrl } from "../api";
import type { SourceSeriesSummary } from "../types";

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
            src={sourceImageUrl(series.cover_url)}
            alt={series.title}
            fill
            className="object-cover transition-transform duration-200 group-hover:scale-105"
            sizes="(max-width: 768px) 50vw, 200px"
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
