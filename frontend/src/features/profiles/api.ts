import { http } from "@/services/http";
import type {
  CreateProfilePayload,
  Profile,
  UpdateProfilePayload,
} from "./types";

/**
 * Thin wrappers over the backend `/profiles` routes. Paths are what the backend
 * serves (in prod the Next proxy strips the `/api` prefix — see next.config.ts).
 * Every call rides the `mm_session` cookie because `http` sends
 * `credentials: "include"`.
 */
export const profilesApi = {
  /** All profiles for the signed-in account, in `sort_order`. */
  list: () => http.get<Profile[]>("/profiles"),

  create: (body: CreateProfilePayload) => http.post<Profile>("/profiles", body),

  update: (id: number, body: UpdateProfilePayload) =>
    http.patch<Profile>(`/profiles/${id}`, body),

  remove: (id: number) => http.delete<void>(`/profiles/${id}`),
};
