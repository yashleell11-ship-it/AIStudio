"use client";

import Image from "next/image";
import Link from "next/link";
import { Globe, ImageOff, Library } from "lucide-react";
import { globalSearchHref } from "@/features/sources/global-search";
import { prettifySourceId } from "@/features/sources/source-branding";
import type { GlobalSearchItem } from "@/features/sources/types";

interface GlobalSearchResultCardProps {
  item: GlobalSearchItem;
  /**
   * Set false inside a per-source section: the section header already names the
   * source, so repeating it on every row is noise.
   */
  showSourceBadge?: boolean;
}

function SourceBadge({ item }: { item: GlobalSearchItem }) {
  if (item.kind === "local") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-cyan-400/30 bg-cyan-400/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-cyan-300">
        <Library className="size-3" aria-hidden />
        Library
      </span>
    );
  }
  const label = prettifySourceId(item.source ?? "source");
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
      <Globe className="size-3" aria-hidden />
      {label}
    </span>
  );
}

export function GlobalSearchResultCard({
  item,
  showSourceBadge = true,
}: GlobalSearchResultCardProps) {
  return (
    <Link href={globalSearchHref(item)}>
      <article className="glass-card group flex gap-4 rounded-2xl p-3 transition-all hover:border-primary/30 hover:shadow-glow">
        <div className="relative h-[120px] w-[80px] shrink-0 overflow-hidden rounded-lg bg-surface-2">
          {item.cover_url ? (
            <Image
              src={item.cover_url}
              alt={item.title}
              fill
              className="object-cover transition-transform duration-300 group-hover:scale-105"
              sizes="80px"
              unoptimized
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-muted/40">
              <ImageOff className="size-6" aria-hidden />
            </div>
          )}
        </div>

        <div className="flex min-w-0 flex-1 flex-col">
          <h3 className="line-clamp-2 text-base font-semibold text-fg group-hover:text-primary">
            {item.title}
          </h3>

          {item.author ? (
            <p className="mt-0.5 truncate text-sm text-muted">{item.author}</p>
          ) : null}

          <div className="mt-auto flex flex-wrap items-center gap-2 pt-3">
            {showSourceBadge ? <SourceBadge item={item} /> : null}
            {item.chapter_count ? (
              <span className="text-xs text-muted">{item.chapter_count} chapters</span>
            ) : null}
          </div>
        </div>
      </article>
    </Link>
  );
}
