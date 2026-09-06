import { ApiError } from "@/types/api";
import { parseUtcTimestamp } from "@/lib/utc-time";
import type { MemberAccount } from "./types";

/**
 * Pure policy behind the Members panel: which rows may be acted on, what the
 * buttons say, how a failure is worded, and what the delete confirmation
 * names. React-free so it is testable under vitest's node environment (the
 * repo has no DOM test renderer).
 */

/** A member as the table shows it, with the caller's own row marked. */
export interface MemberRow {
  member: MemberAccount;
  /** True for the signed-in admin's own account. */
  isSelf: boolean;
}

/**
 * Display order: the caller's own account first, then everyone else in the
 * order they joined.
 *
 * Self leads because it is the one row whose buttons are disabled, and a
 * disabled row is easier to explain at the top than found by surprise halfway
 * down. Joined order rather than alphabetical because the question this table
 * answers is "who signed up?", and the bottom of the list is where a new name
 * is looked for. Ties (same second) fall back to id, which is also join order.
 */
export function shapeMemberRows(
  members: readonly MemberAccount[],
  currentUserId: number | null | undefined,
): MemberRow[] {
  return [...members]
    .sort((a, b) => {
      const aSelf = a.id === currentUserId;
      const bSelf = b.id === currentUserId;
      if (aSelf !== bSelf) return aSelf ? -1 : 1;
      const joined =
        (parseUtcTimestamp(a.created_at) ?? 0) - (parseUtcTimestamp(b.created_at) ?? 0);
      return joined !== 0 ? joined : a.id - b.id;
    })
    .map((member) => ({ member, isSelf: member.id === currentUserId }));
}

/** What the row's controls may do, and why not when they may not. */
export interface MemberRowGuard {
  isSelf: boolean;
  canToggleActive: boolean;
  canDelete: boolean;
  /** Attached to the disabled buttons; null when nothing is blocked. */
  reason: string | null;
}

export const SELF_ROW_REASON =
  "This is your own account. It can't be deactivated or deleted from here.";

/**
 * The self-row guard.
 *
 * `PATCH` and `DELETE /auth/users/{id}` both answer 400 for the caller's own
 * id, so the server would refuse anyway — but a button that always fails is
 * worse than one that is visibly off, and an admin who deactivates themselves
 * has no way back in. Both controls are therefore disabled on the caller's
 * row, with the reason attached.
 *
 * `currentUserId` is nullable because `/auth/me` may not have answered yet.
 * While it is unknown, NO row is treated as self — an unknown caller is never
 * given a free pass to act on any row, but nor is every row locked; the panel
 * itself does not render until `is_admin` is known, which is the same moment
 * the id is.
 */
export function memberRowGuard(
  member: Pick<MemberAccount, "id">,
  currentUserId: number | null | undefined,
): MemberRowGuard {
  const isSelf = currentUserId != null && member.id === currentUserId;
  return {
    isSelf,
    canToggleActive: !isSelf,
    canDelete: !isSelf,
    reason: isSelf ? SELF_ROW_REASON : null,
  };
}

/** The toggle's label reads as the action it will take, not the state it is in. */
export function activeToggleLabel(isActive: boolean): "Deactivate" | "Reactivate" {
  return isActive ? "Deactivate" : "Reactivate";
}

/**
 * Copy for the delete confirmation. Names the account in both the title and
 * the body so the wrong row cannot be confirmed out of habit.
 */
export interface DeleteMemberConfirmation {
  title: string;
  body: string;
  /** The confirm button's label. */
  action: string;
}

export function deleteMemberConfirmation(
  member: Pick<MemberAccount, "username">,
): DeleteMemberConfirmation {
  return {
    title: `Delete ${member.username}?`,
    body:
      `This removes ${member.username}'s account and everything it owns — ` +
      "every profile, followed series, reading progress, bookmarks, collections " +
      "and sessions. There is no undo. Export a backup first if you might want " +
      "any of it back.",
    action: `Delete ${member.username}`,
  };
}

/** "3 sessions", "1 session", "No sessions". */
export function formatSessionCount(count: number): string {
  if (count <= 0) return "No sessions";
  return count === 1 ? "1 session" : `${count} sessions`;
}

/** The footnote under the table: how many accounts besides the caller's. */
export function describeOtherMembers(rows: readonly MemberRow[]): string {
  const others = rows.filter((row) => !row.isSelf).length;
  if (others === 0) return "Only your account so far. Anyone who registers appears here.";
  return others === 1 ? "1 other account." : `${others} other accounts.`;
}

/**
 * What to show when an admin call fails.
 *
 * The server's own wording is passed through: it is the only thing that knows
 * why a change was refused (the 400 for targeting yourself, say), and it has
 * already decided how much to say. `fallback` covers the responses that never
 * went through the `{code, message}` envelope at all — a proxy's 502 — where
 * `ApiError` has nothing better than the status to report.
 */
export function describeMembersFailure(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.code !== "unknown_error") return error.message;
    return `${fallback} (HTTP ${error.status})`;
  }
  return fallback;
}
