"use client";

import Image from "next/image";
import { BookOpen } from "lucide-react";
import { cn } from "@/lib/cn";

interface BookPlateProps {
  /** Already resolved to a fetchable URL, or null when the source gave none. */
  coverUrl: string | null;
  title: string;
  /** Size and shape of the plate — the shelf and the front matter differ. */
  className: string;
  /** `next/image` sizes hint. */
  sizes: string;
  /**
   * Empty on the shelf, where the title is the very next thing read out; the
   * title on the front matter, where the plate is the only image on the page.
   */
  alt?: string;
}

/**
 * A cover, quietly.
 *
 * A 1px rule and nothing else — no shadow, no hover lift, no spine. Novel
 * covers are usually an aggregator's generated placeholder and sometimes there
 * is no cover at all, so "none" is a real state with its own quiet mark rather
 * than a broken image: `cover_url` comes back as an empty string from a source
 * that has nothing, and resolving that against the API base would produce a URL
 * that loads the backend root as an image.
 */
export function BookPlate({ coverUrl, title, className, sizes, alt = "" }: BookPlateProps) {
  if (!coverUrl) {
    return (
      <div
        className={cn(
          "flex shrink-0 items-center justify-center rounded-sm border border-border bg-surface-2",
          className,
        )}
        role="img"
        aria-label={alt || `No cover for ${title}`}
      >
        <BookOpen className="size-4 text-muted" aria-hidden />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "relative shrink-0 overflow-hidden rounded-sm border border-border bg-surface-2",
        className,
      )}
    >
      <Image src={coverUrl} alt={alt} fill className="object-cover" sizes={sizes} unoptimized />
      {alt ? null : <span className="sr-only">{title}</span>}
    </div>
  );
}
