"use client";

import Image from "next/image";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
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
      <Card className="group overflow-hidden transition-colors hover:border-primary/40">
        <div className="relative aspect-[2/3] w-full overflow-hidden bg-surface-2">
          <Image
            src={sourceImageUrl(series.cover_url)}
            alt={series.title}
            fill
            className="object-cover transition-transform group-hover:scale-[1.02]"
            sizes="(max-width: 768px) 50vw, 200px"
            unoptimized
          />
          {series.status && (
            <Badge variant="primary" className="absolute left-2 top-2 capitalize">
              {series.status}
            </Badge>
          )}
        </div>
        <div className="p-3">
          <h3 className="line-clamp-2 font-medium text-fg">{series.title}</h3>
          {series.author && (
            <p className="mt-1 truncate text-sm text-muted">{series.author}</p>
          )}
          {series.latest_chapter && (
            <p className="mt-2 text-xs text-muted">Latest: {series.latest_chapter}</p>
          )}
          {series.genres.length > 0 && (
            <p className="mt-2 line-clamp-1 text-xs text-muted">
              {series.genres.join(" · ")}
            </p>
          )}
        </div>
      </Card>
    </Link>
  );
}
