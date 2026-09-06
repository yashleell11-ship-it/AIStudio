/**
 * Account administration (`/auth/users`, admin-only on the server).
 *
 * Registration on this instance is open on purpose, so the owner needs to see
 * who has signed up and be able to switch an account off or remove it. Every
 * route here carries the server's admin check; the panel re-checks `is_admin`
 * on the client only so a non-admin never sees a table whose every button
 * would answer 403.
 */

/** One row of `GET /auth/users`. */
export interface MemberAccount {
  id: number;
  username: string;
  is_admin: boolean;
  /** False once deactivated: the account and its data stay, sign-in is refused. */
  is_active: boolean;
  created_at: string;
  /** Null for an account that registered and has not signed in since. */
  last_login_at: string | null;
  /** Live sessions on the account right now. */
  session_count: number;
}

/** Body of `PATCH /auth/users/{id}`. */
export interface SetMemberActivePayload {
  is_active: boolean;
}
