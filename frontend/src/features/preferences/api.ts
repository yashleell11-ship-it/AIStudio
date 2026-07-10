import { http } from "@/services/http";

/**
 * The slice of the unified `/settings` payload this feature reads/writes.
 * The endpoint returns more (downloads, updates, ocr, …); we only touch the
 * mature-content gate here.
 */
export interface ContentPreferences {
  mature_content_enabled: boolean;
}

export const preferencesApi = {
  get: () => http.get<ContentPreferences>("/settings"),

  setMatureContent: (enabled: boolean) =>
    http.put<ContentPreferences>("/settings", { mature_content_enabled: enabled }),
};
