"use client";

import Image from "next/image";
import Link from "next/link";
import { libraryCoverUrl } from "../api";
import type { FollowedSeries } from "../types";

/**
 * A cover-first Library card for one followed series. Cover, title, and a single
 * muted meta line.
 */
export function FollowedSeriesCard({ series }: { series: FollowedSeries }) {
  const subtitle =
    series.chapter_count > 0
      ? series.chapter_count === 1
        ? "1 chapter"
        : `${series.chapter_count} chapters`
      : null;

  return (
    <Link
      href={`/library/${series.id}`}
      className="group block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <div className="relative aspect-[2/3] w-full overflow-hidden rounded-xl bg-surface-2">
        <Image
          src={libraryCoverUrl(series.cover_url)}
          alt={series.title}
          fill
          className="object-cover transition-transform duration-300 group-hover:scale-105"
          sizes="(max-width: 640px) 45vw, (max-width: 1024px) 30vw, 200px"
          unoptimized
        />
      </div>

      <h3 className="mt-2 line-clamp-2 text-sm font-semibold leading-tight text-fg">
        {series.title}
      </h3>
      {subtitle ? (
        <p className="mt-0.5 truncate text-xs text-muted">{subtitle}</p>
      ) : null}
    </Link>
  );
}
