import { http } from "@/services/http";
import type { MemberAccount, SetMemberActivePayload } from "./types";

/**
 * Thin wrappers over the admin half of `/auth`. Kept here rather than in
 * `features/auth/api.ts` because these are the owner's controls over OTHER
 * accounts, not the caller's own — a different audience and a different blast
 * radius.
 *
 * Every call rides the `mm_session` cookie (`http` sends
 * `credentials: "include"`) and is refused with 403 to a non-admin.
 */
export const adminApi = {
  /** Every account on the instance, the caller's own included. */
  users: () => http.get<MemberAccount[]>("/auth/users"),

  /**
   * Switch an account on or off. Returns the updated row. 400 when the id is
   * the caller's own — the server refuses to let an admin lock themselves out.
   */
  setActive: (userId: number, isActive: boolean) =>
    http.patch<MemberAccount>(`/auth/users/${userId}`, {
      is_active: isActive,
    } satisfies SetMemberActivePayload),

  /**
   * Remove an account and everything it owns: profiles, followed series,
   * progress, bookmarks, collections, sessions. 204. 400 for the caller's own id.
   */
  deleteUser: (userId: number) => http.delete<void>(`/auth/users/${userId}`),
};
