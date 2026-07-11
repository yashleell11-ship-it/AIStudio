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
  /** True while zero accounts exist — show "create the first admin" instead of login. */
  needs_bootstrap: boolean;
  /** Whether self-service registration is open once an admin exists. */
  registration_enabled: boolean;
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
  remember?: boolean;
}
