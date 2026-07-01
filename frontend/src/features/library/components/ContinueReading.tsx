"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { ContinueReadingItem } from "../types";

interface ContinueReadingProps {
  items: ContinueReadingItem[];
}

export function ContinueReading({ items }: ContinueReadingProps) {
  if (items.length === 0) return null;

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
        Continue Reading
      </h2>
      <div className="flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory scroll-smooth">
        {items.map((item) => (
          <Link
            key={item.series_id}
            href={`/reader/${item.series_id}/${item.chapter_id}?page=${item.last_page}`}
            className="min-w-[220px] shrink-0 snap-start"
          >
            <Card className="p-4 transition-colors hover:border-primary/40">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium text-fg">{item.series_title}</p>
                  <p className="mt-1 truncate text-sm text-muted">{item.chapter_title}</p>
                  <p className="mt-2 text-xs text-muted">Page {item.last_page}</p>
                </div>
                <Badge variant="primary">{Math.round(item.progress_pct)}%</Badge>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </section>
  );
}
