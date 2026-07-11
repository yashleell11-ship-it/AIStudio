import { http } from "@/services/http";
import type {
  AuthResponse,
  BootstrapStatus,
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

  /** The "am I authenticated?" probe: 200 User when signed in, 401 when not. */
  me: () => http.get<User>("/auth/me"),
};
