"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useImportLibrary } from "../hooks";

interface ImportDialogProps {
  open: boolean;
  onClose: () => void;
}

export function ImportDialog({ open, onClose }: ImportDialogProps) {
  const [folderPath, setFolderPath] = useState("");
  const importMutation = useImportLibrary();

  const handleImport = async () => {
    if (!folderPath.trim()) return;
    try {
      await importMutation.mutateAsync(folderPath.trim());
      setFolderPath("");
      onClose();
    } catch {
      // Error surfaced via importMutation.error
    }
  };

  const error = importMutation.error?.message ?? null;

  return (
    <Dialog open={open} onClose={onClose} title="Import Library" className="max-w-md">
      <div className="space-y-4">
        <p className="text-sm text-muted">
          Enter the absolute path to your library folder on this machine. ManhwaManiacs
          indexes files in place — nothing is copied.
        </p>
        <Input
          value={folderPath}
          onChange={(event) => setFolderPath(event.target.value)}
          placeholder="D:\Comics\My Library"
          disabled={importMutation.isPending}
          aria-label="Library folder path"
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={importMutation.isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleImport}
            disabled={!folderPath.trim() || importMutation.isPending}
          >
            {importMutation.isPending ? "Importing…" : "Import"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
