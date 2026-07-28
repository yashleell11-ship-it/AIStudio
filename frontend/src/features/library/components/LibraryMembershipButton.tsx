"use client";

import { useState } from "react";
import { BookmarkCheck, BookmarkPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/cn";
import { useLibraryMembership, useSetLibraryMembership } from "../hooks";

interface LibraryMembershipButtonProps {
  seriesId: number;
  /**
   * Whether the series is on the active profile's shelf: `in_library` from the
   * series payload, or `true` for a series that came out of a membership-gated
   * list and is therefore a member by construction.
   */
  inLibrary: boolean;
  /** Icon-only rendering for dense surfaces such as the grid card. */
  compact?: boolean;
  className?: string;
}

/**
 * The add/remove-from-library control.
 *
 * `POST`/`DELETE /library/series/{id}/add` is the only way a profile gets a
 * series onto its shelf, and without it a catalog series stays invisible to
 * every gated read with no way back. Removing keeps favourites, reading status
 * and progress server-side, so this is a genuine toggle, not a delete.
 */
export function LibraryMembershipButton({
  seriesId,
  inLibrary: seed,
  compact = false,
  className,
}: LibraryMembershipButtonProps) {
  const membership = useLibraryMembership(seriesId, seed);
  const mutation = useSetLibraryMembership();
  const [error, setError] = useState<string | null>(null);

  // The mutation's optimistic write wins over the payload's answer while a
  // toggle is in flight, so the label flips on click rather than on refetch.
  const inLibrary = membership.data === true;
  const busy = mutation.isPending;

  const toggle = async () => {
    setError(null);
    try {
      await mutation.mutateAsync({ seriesId, inLibrary: !inLibrary });
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Failed to update your library.",
      );
    }
  };

  const label = inLibrary ? "Remove from library" : "Add to library";
  const Icon = inLibrary ? BookmarkCheck : BookmarkPlus;

  if (compact) {
    return (
      <button
        type="button"
        onClick={(event) => {
          // The card is wrapped in a Link; keep the click on the button.
          event.preventDefault();
          event.stopPropagation();
          void toggle();
        }}
        disabled={busy}
        aria-label={label}
        title={error ?? label}
        className={cn(
          "z-10 flex size-8 items-center justify-center rounded-full bg-black/50 backdrop-blur-sm transition-colors disabled:opacity-50",
          inLibrary ? "text-primary" : "text-white/70 hover:text-white",
          error && "text-danger",
          className,
        )}
      >
        <Icon className="size-4" aria-hidden />
      </button>
    );
  }

  return (
    <div className={cn("flex flex-col items-start gap-1", className)}>
      <Button
        variant={inLibrary ? "secondary" : "primary"}
        disabled={busy}
        onClick={() => void toggle()}
        aria-label={label}
      >
        <Icon className="size-4" aria-hidden />
        {inLibrary ? "In library" : "Add to library"}
      </Button>
      {error ? <p className="text-xs text-danger">{error}</p> : null}
    </div>
  );
}
