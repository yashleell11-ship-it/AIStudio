"use client";

import Image from "next/image";
import Link from "next/link";
import { BookOpen, SearchX, TriangleAlert } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/cn";
import { shelfBlurb, shelfGenres, shelfMetaParts, type ShelfBook } from "../shelf";

interface NovelShelfProps {
  books: ShelfBook[];
  isLoading?: boolean;
  /** Rendered when the shelf is empty. Callers word their own. */
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: { label: string; href: string };
  errorMessage?: string;
  onRetry?: () => void;
  className?: string;
}

/**
 * A shelf of books.
 *
 * Not a grid of posters: one book to a row, divided by hairlines, leading with
 * the title in serif and the facts a novel is recognised by underneath. Covers
 * are present but small and quiet — real art still aids recognition, and most
 * novel covers are not real art.
 *
 * The rows use the app's own tokens and spacing, not a reading palette: this is
 * a screen in the app, and only the reader is a page of a book.
 */
export function NovelShelf({
  books,
  isLoading,
  emptyTitle = "Nothing on this shelf",
  emptyDescription = "Nothing here yet.",
  emptyAction,
  errorMessage,
  onRetry,
  className,
}: NovelShelfProps) {
  if (errorMessage) {
    return (
      <EmptyState
        tone="error"
        icon={TriangleAlert}
        title="Couldn't load these books"
        description={errorMessage}
        action={onRetry ? { label: "Try again", onClick: onRetry } : undefined}
      />
    );
  }

  if (isLoading) {
    return <NovelShelfSkeleton className={className} />;
  }

  if (books.length === 0) {
    return (
      <EmptyState
        icon={SearchX}
        title={emptyTitle}
        description={emptyDescription}
        action={emptyAction}
      />
    );
  }

  return (
    <ul className={cn("divide-y divide-border border-y border-border", className)}>
      {books.map((book) => (
        <ShelfRow key={book.key} book={book} />
      ))}
    </ul>
  );
}

function ShelfRow({ book }: { book: ShelfBook }) {
  const meta = shelfMetaParts(book);
  const genres = shelfGenres(book.genres);
  const blurb = shelfBlurb(book.description);

  return (
    <li>
      <Link
        href={book.href}
        className="group flex gap-4 px-1 py-4 transition-colors hover:bg-fg/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 sm:px-2"
      >
        <BookPlate coverUrl={book.coverUrl} title={book.title} />

        <div className="min-w-0 flex-1">
          <h3 className="font-book text-lg leading-snug text-fg transition-colors group-hover:text-primary">
            {book.title}
          </h3>

          {meta.length > 0 ? (
            <p className="mt-1 text-sm text-muted">{meta.join(" · ")}</p>
          ) : null}

          {blurb ? (
            <p className="mt-2 line-clamp-2 font-book text-sm leading-relaxed text-muted">
              {blurb}
            </p>
          ) : null}

          {genres.length > 0 ? (
            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-muted/80">
              {genres.join(" · ")}
            </p>
          ) : null}
        </div>
      </Link>
    </li>
  );
}

/**
 * The cover, small.
 *
 * A 1px rule and nothing else — no shadow, no hover lift, no spine. When a
 * source has no cover at all the plate falls back to a plain mark rather than a
 * broken image, which is the common case on a public-domain archive.
 */
function BookPlate({ coverUrl, title }: { coverUrl: string | null; title: string }) {
  if (!coverUrl) {
    return (
      <div
        className="flex h-[4.25rem] w-12 shrink-0 items-center justify-center rounded-sm border border-border bg-surface-2"
        aria-hidden
      >
        <BookOpen className="size-4 text-muted" />
      </div>
    );
  }

  return (
    <div className="relative h-[4.25rem] w-12 shrink-0 overflow-hidden rounded-sm border border-border bg-surface-2">
      <Image
        src={coverUrl}
        alt=""
        fill
        className="object-cover"
        sizes="48px"
        unoptimized
      />
      <span className="sr-only">{title}</span>
    </div>
  );
}

function NovelShelfSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("divide-y divide-border border-y border-border", className)}
      aria-busy="true"
      aria-label="Loading books"
    >
      {Array.from({ length: 8 }).map((_, index) => (
        <div key={index} className="flex gap-4 px-1 py-4 sm:px-2">
          <div className="h-[4.25rem] w-12 shrink-0 animate-pulse rounded-sm bg-surface-2" />
          <div className="min-w-0 flex-1 space-y-2 py-0.5">
            <div className="h-4 w-1/2 animate-pulse rounded bg-surface-2" />
            <div className="h-3 w-1/3 animate-pulse rounded bg-surface-2" />
            <div className="h-3 w-full animate-pulse rounded bg-surface-2" />
          </div>
        </div>
      ))}
    </div>
  );
}
