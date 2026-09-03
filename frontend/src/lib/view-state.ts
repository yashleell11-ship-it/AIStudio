import { ApiError } from "@/types/api";
import { isNetworkUnreachableError } from "@/features/offline/session-gate";

/**
 * Which of four ways a data-driven screen can look right now. Screens compute
 * this from a query's `{isLoading, error, data}` and switch on it once,
 * instead of each re-deriving its own `if (isLoading) ... else if (error)
 * ...` chain — pairs with `EmptyState` (`components/ui/empty-state.tsx`),
 * which renders the "empty" / "error" / "offline" cases.
 *
 * `"offline"` is split out from `"error"` on purpose (spec §5: distinguish
 * "nothing here" from "couldn't load", and an unreachable server should say so
 * and point at what still works, not read like every other failure).
 */
export type ViewState = "loading" | "offline" | "error" | "empty" | "content";

export interface ResolveViewStateInput {
  isLoading: boolean;
  error: unknown;
  /** Whether the resolved data has zero items. Ignored while loading or errored. */
  isEmpty: boolean;
}

export function resolveViewState({
  isLoading,
  error,
  isEmpty,
}: ResolveViewStateInput): ViewState {
  if (isLoading) return "loading";
  if (error) return isNetworkUnreachableError(error) ? "offline" : "error";
  return isEmpty ? "empty" : "content";
}

/**
 * A message safe to render for a thrown query error. `ApiError.message` is
 * already UI-safe (see `services/http.ts`); anything else (a thrown non-Error,
 * a bug) falls back to caller-supplied copy rather than `String(error)`, which
 * could leak something stack-shaped onto the screen.
 */
export function apiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}
