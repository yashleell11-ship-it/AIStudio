"use client";

import Link from "next/link";
import { Check, SearchX, TriangleAlert } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/cn";
import { shelfBlurb, shelfGenres, shelfMetaParts, type ShelfBook } from "../shelf";
import { BookPlate } from "./BookPlate";

/**
 * Multi-select over a shelf, for the library.
 *
 * Addressed by `ShelfBook` rather than by an id, because a shelf row is a view
 * model with a string key and the library's own selection is keyed by the
 * numeric follow-row id. The caller closes over its own lookup; the shelf never
 * learns what a follow row is.
 */
export interface NovelShelfSelection {
  selecting: boolean;
  isSelected: (book: ShelfBook) => boolean;
  onSelect: (book: ShelfBook, shiftKey: boolean) => void;
}

interface NovelShelfProps {
  books: ShelfBook[];
  isLoading?: boolean;
  /** Rendered when the shelf is empty. Callers word their own. */
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: { label: string; href: string };
  errorMessage?: string;
  onRetry?: () => void;
  /** Omitted by shelves with no multi-select (browse, search). */
  selection?: NovelShelfSelection;
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
  selection,
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
    <ul
      className={cn(
        "divide-y divide-border border-y border-border",
        // Shift-click otherwise drags the browser's own text selection across
        // every row it passes, which looks like a bug.
        selection?.selecting && "select-none",
        className,
      )}
    >
      {books.map((book) => (
        <ShelfRow key={book.key} book={book} selection={selection} />
      ))}
    </ul>
  );
}

function ShelfRow({
  book,
  selection,
}: {
  book: ShelfBook;
  selection?: NovelShelfSelection;
}) {
  const meta = shelfMetaParts(book);
  const genres = shelfGenres(book.genres);
  const blurb = shelfBlurb(book.description);
  const selecting = selection?.selecting ?? false;
  const selected = selecting && (selection?.isSelected(book) ?? false);

  const rowClassName = cn(
    "group flex w-full gap-4 px-1 py-4 text-left transition-colors hover:bg-fg/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 sm:px-2",
    selected && "bg-primary/[0.07]",
  );

  const body = (
    <>
      {selecting ? (
        <span
          aria-hidden
          className={cn(
            "mt-1 flex size-5 shrink-0 items-center justify-center rounded border transition-colors",
            selected
              ? "border-primary bg-primary text-primary-fg"
              : "border-border bg-transparent",
          )}
        >
          {selected ? <Check className="size-3.5" /> : null}
        </span>
      ) : null}

      <BookPlate
        coverUrl={book.coverUrl}
        title={book.title}
        className="h-[4.25rem] w-12"
        sizes="48px"
      />

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
    </>
  );

  // While selecting, the row picks rather than opens — a link that sometimes
  // navigates and sometimes toggles is the worst of both.
  if (selecting) {
    return (
      <li>
        <button
          type="button"
          role="checkbox"
          aria-checked={selected}
          onClick={(event) => selection?.onSelect(book, event.shiftKey)}
          className={rowClassName}
        >
          {body}
        </button>
      </li>
    );
  }

  return (
    <li>
      <Link href={book.href} className={rowClassName}>
        {body}
      </Link>
    </li>
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
