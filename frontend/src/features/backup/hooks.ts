import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { backupApi } from "./api";
import { backupDownloadFilename } from "./backup-file";
import { saveBlobAsFile } from "./save-blob";

const BACKUP_KEY = ["backup"] as const;

/**
 * Whether a restore is staged. Polled: the pending flag also clears from
 * outside the browser — the next server start applies the staged file — and a
 * banner that keeps promising a restore already applied is worse than no
 * banner.
 */
export function useBackupStatus() {
  return useQuery({
    queryKey: [...BACKUP_KEY, "status"],
    queryFn: () => backupApi.status(),
    refetchInterval: 30_000,
  });
}

/** Downloads the snapshot. Nothing on the server changes, so nothing is invalidated. */
export function useExportBackup() {
  return useMutation({
    mutationFn: async () => {
      const { blob, contentDisposition } = await backupApi.exportDatabase();
      const filename = backupDownloadFilename(contentDisposition, new Date());
      saveBlobAsFile(blob, filename);
      return filename;
    },
  });
}

export function useImportBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => backupApi.importDatabase(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BACKUP_KEY });
    },
  });
}

export function useCancelPendingRestore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => backupApi.cancelPendingRestore(),
    onSuccess: (status) => {
      queryClient.setQueryData([...BACKUP_KEY, "status"], status);
    },
  });
}
