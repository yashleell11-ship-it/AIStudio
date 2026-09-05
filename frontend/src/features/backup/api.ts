import { http, requestBlob, type BlobResponse } from "@/services/http";
import type { BackupStatus, RestoreStaged } from "./types";

export const backupApi = {
  status: () => http.get<BackupStatus>("/backup/status"),

  /** Streams the snapshot; the session cookie rides along (see `requestBlob`). */
  exportDatabase: (): Promise<BlobResponse> => requestBlob("/backup/export"),

  /** Field name `file` — it is what `import_backup(file: UploadFile)` binds. */
  importDatabase: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return http.post<RestoreStaged>("/backup/import", form);
  },

  cancelPendingRestore: () => http.delete<BackupStatus>("/backup/pending"),
};
