"use client";

import Image from "next/image";
import Link from "next/link";
import { libraryCoverUrl } from "../api";
import type { FollowedSeries } from "../types";

/**
 * The shelf grid's cell: `grid-cols-3 gap-x-3` inside the view's `px-5`, which
 * is `calc(33.33vw - 21px)` — 104px on a 375px phone. The widest it reaches is
 * the 8-up `lg` row. This string is both the browser's `sizes` hint and what
 * the cover proxy renders to (`lib/cover-url.ts`), so it states the real cell
 * rather than a round `vw`.
 */
const COVER_SIZES = "(max-width: 639px) calc(33.33vw - 21px), 180px";

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
          src={libraryCoverUrl(series.cover_url, COVER_SIZES)}
          alt={series.title}
          fill
          className="object-cover transition-transform duration-300 group-hover:scale-105"
          sizes={COVER_SIZES}
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
