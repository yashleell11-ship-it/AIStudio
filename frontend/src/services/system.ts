import { http } from "./http";

/** Health/status payload returned by the backend root route. */
export interface SystemStatus {
  status: string;
  name: string;
  version: string;
}

export const systemService = {
  getStatus: (signal?: AbortSignal) => http.get<SystemStatus>("/", { signal }),
};
