"use client";

import Image from "next/image";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { sourceImageUrl } from "../api";
import type { SourceSeriesSummary } from "../types";

interface SourceSeriesCardProps {
  sourceId: string;
  series: SourceSeriesSummary;
}

export function SourceSeriesCard({ sourceId, series }: SourceSeriesCardProps) {
  return (
    <Link href={`/sources/${sourceId}/series/${encodeURIComponent(series.id)}`}>
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
