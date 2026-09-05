import { http } from "@/services/http";
import type {
  AccountSession,
  AuthResponse,
  BootstrapStatus,
  ChangePasswordPayload,
  LoginPayload,
  RegisterPayload,
  User,
} from "./types";

/**
 * Thin wrappers over the backend `/auth` routes. Paths are what the backend
 * serves (in prod the Next proxy strips the `/api` prefix — see next.config.ts).
 * Every call rides the `mm_session` cookie because `http` sends
 * `credentials: "include"`.
 */
export const authApi = {
  /** Public: decides whether to show first-admin bootstrap vs. normal login. */
  bootstrapStatus: () => http.get<BootstrapStatus>("/auth/bootstrap-status"),

  register: (body: RegisterPayload) => http.post<AuthResponse>("/auth/register", body),

  login: (body: LoginPayload) => http.post<AuthResponse>("/auth/login", body),

  logout: () => http.post<void>("/auth/logout"),

  /** Revoke every session for this account, this one included. 204. */
  logoutAll: () => http.post<void>("/auth/logout-all"),

  /** The "am I authenticated?" probe: 200 User when signed in, 401 when not. */
  me: () => http.get<User>("/auth/me"),

  /**
   * Rotate the password. 204 on success; 401 `invalid_credentials` when the
   * current password is wrong, 422 `weak_password` when the new one is
   * rejected. The server revokes every OTHER session on success and keeps
   * this one — no follow-up call is needed to sign the other devices out.
   *
   * Sent as a POST body, never a query string: `http` puts `query` in the URL,
   * and a URL is the one place a secret must never appear.
   */
  changePassword: (body: ChangePasswordPayload) =>
    http.post<void>("/auth/change-password", body),

  /** This account's live sessions, newest-used first, with `current` marked. */
  sessions: () => http.get<AccountSession[]>("/auth/sessions"),

  /** Revoke one session by id. 204, or 404 `not_found` if it is already gone. */
  revokeSession: (sessionId: number) => http.delete<void>(`/auth/sessions/${sessionId}`),
};
