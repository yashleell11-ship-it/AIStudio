/**
 * Contracts for the backend auth surface (routes under `/auth`).
 * The web client authenticates via the httpOnly `mm_session` cookie the backend
 * sets on login/register; the `token` field on `AuthResponse` is for the mobile
 * Bearer flow and is ignored here.
 */

export interface User {
  id: number;
  username: string;
  email: string | null;
  display_name: string | null;
  is_admin: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuthResponse {
  user: User;
  /** Bearer token for mobile clients. The web client relies on the cookie. */
  token: string;
}

export interface BootstrapStatus {
  /**
   * True while zero accounts exist. Kept for older callers; screen-mode logic
   * should key off `bootstrap_open` instead — an empty table whose takeover
   * window has expired no longer grants uninvited signup (see
   * `backend/routes/auth.py`).
   */
  needs_bootstrap: boolean;
  /**
   * True while zero accounts exist AND the bootstrap takeover window is still
   * open: registering right now needs no invite code and yields the admin
   * account. Optional/absent on an older backend — fall back to
   * `needs_bootstrap`, which is what "bootstrap" meant before this window
   * existed.
   */
  bootstrap_open?: boolean;
  /** The deployment's self-service registration switch (post-bootstrap). */
  registration_enabled: boolean;
  /**
   * Whether `POST /auth/register` requires an `invite_code` right now.
   * Optional/absent on an older backend — treat a missing value as "not
   * required" so the client degrades gracefully.
   */
  invite_code_required?: boolean;
  /**
   * Convenience: can `POST /auth/register` succeed at all right now (with a
   * valid invite code where required)? False hides/disables the signup
   * form entirely. Optional/absent on an older backend — fall back to
   * `registration_enabled`.
   */
  registration_open?: boolean;
  /**
   * Whether this deployment serves novels (`MM_NOVELS_ENABLED`).
   *
   * Rides on the bootstrap read rather than getting a config endpoint of its
   * own because this is the pre-auth config surface the clients already
   * fetch. Optional/absent on a backend that predates the flag — which is the
   * same thing as off, and is read that way (`features/novels/gate.ts`).
   *
   * False means the app must look EXACTLY as it did before novels existed:
   * no reader route, no mode switch, nothing.
   */
  novels_enabled?: boolean;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

/**
 * One row of `GET /auth/sessions` — the backend's `SessionOut`. `current` is
 * computed per-request by comparing the row's token hash against the caller's
 * own token, so it is only meaningful on the response that produced it.
 */
export interface AccountSession {
  id: number;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  /** The `User-Agent` recorded at login; null when the client sent none. */
  user_agent: string | null;
  ip_address: string | null;
  /** True for the session making the request. */
  current: boolean;
}

export interface LoginPayload {
  username: string;
  password: string;
  remember?: boolean;
}

export interface RegisterPayload {
  username: string;
  password: string;
  email?: string | null;
  display_name?: string | null;
  /** Required only when `BootstrapStatus.invite_code_required` is true. */
  invite_code?: string | null;
  remember?: boolean;
}
