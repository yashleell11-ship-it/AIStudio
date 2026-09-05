"use client";

import { useRef, useState } from "react";
import { DatabaseBackup, Download, FileUp, Hourglass, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { formatBytes } from "@/features/offline/format";
import { cn } from "@/lib/cn";
import {
  describeBackupFailure,
  isRestoreConfirmed,
  RESTORE_CONFIRMATION_PHRASE,
  validateBackupSelection,
} from "../backup-file";
import {
  useBackupStatus,
  useCancelPendingRestore,
  useExportBackup,
  useImportBackup,
} from "../hooks";

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">
      {children}
    </h3>
  );
}

/**
 * `announce` is on for anything that appears in response to an action — a
 * restore that failed silently is the failure this whole screen exists to
 * avoid. It is off for standing copy, which is already read in document order.
 */
function Alert({
  tone,
  announce = true,
  children,
}: {
  tone: "danger" | "warning";
  announce?: boolean;
  children: React.ReactNode;
}) {
  const danger = tone === "danger";
  return (
    <div
      role={announce ? "alert" : undefined}
      className={cn(
        "flex items-start gap-3 rounded-xl border p-3",
        danger ? "border-danger/30 bg-danger/10" : "border-warning/30 bg-warning/10",
      )}
    >
      <TriangleAlert
        className={cn("mt-0.5 size-4 shrink-0", danger ? "text-danger" : "text-warning")}
        aria-hidden
      />
      <div className="min-w-0 text-sm text-fg/90">{children}</div>
    </div>
  );
}

/** The staged-restore banner: the one state where this page owes an explanation. */
function PendingRestoreBanner({
  onCancel,
  cancelling,
}: {
  onCancel: () => void;
  cancelling: boolean;
}) {
  return (
    <div className="mb-6 rounded-xl border border-warning/40 bg-warning/10 p-4">
      <p className="flex items-center gap-2 text-sm font-medium text-warning">
        <Hourglass className="size-4" aria-hidden />
        Restore staged
      </p>
      <p className="mt-1 text-sm text-fg/90">
        A backup has been validated and is waiting. It replaces this server&apos;s
        database the next time the server restarts. Nothing has changed yet.
      </p>
      <Button
        variant="secondary"
        className="mt-3"
        onClick={onCancel}
        disabled={cancelling}
      >
        {cancelling ? "Cancelling…" : "Cancel staged restore"}
      </Button>
    </div>
  );
}

/**
 * Backup and restore for the whole instance — the web half of what
 * `mobile/lib/features/settings/screens/backup_screen.dart` has always had.
 *
 * Admin-only, because the endpoints are (`require_admin_user` on export,
 * import and cancel) and because the file is the entire SQLite database: every
 * account on this instance, not one profile's reading data.
 *
 * There is deliberately no drop target. Restore is the most destructive action
 * in the product, and a drag that ends in the wrong place must not be able to
 * start it — the only route in is the picker, then a typed confirmation.
 */
export function BackupPanel() {
  const status = useBackupStatus();
  const exportBackup = useExportBackup();
  const importBackup = useImportBackup();
  const cancelRestore = useCancelPendingRestore();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [stagedMessage, setStagedMessage] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportedName, setExportedName] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  const restorePending = status.data?.restore_pending ?? false;

  const runExport = async () => {
    setExportError(null);
    setExportedName(null);
    try {
      setExportedName(await exportBackup.mutateAsync());
    } catch (error) {
      setExportError(
        describeBackupFailure(error, "The backup could not be downloaded."),
      );
    }
  };

  const chooseFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRestoreError(null);
    setStagedMessage(null);
    const file = event.target.files?.[0] ?? null;
    // Clearing the input lets the same file be picked again after a failure.
    event.target.value = "";
    if (!file) return;

    const check = validateBackupSelection(file);
    if (!check.ok) {
      setSelectedFile(null);
      setRestoreError(check.message);
      return;
    }
    setSelectedFile(file);
  };

  const openConfirm = () => {
    setConfirmText("");
    setRestoreError(null);
    setConfirmOpen(true);
  };

  const closeConfirm = () => {
    setConfirmOpen(false);
    setConfirmText("");
  };

  const confirmRestore = async () => {
    if (!selectedFile || !isRestoreConfirmed(confirmText)) return;
    try {
      const staged = await importBackup.mutateAsync(selectedFile);
      closeConfirm();
      setSelectedFile(null);
      setStagedMessage(staged.message);
    } catch (error) {
      closeConfirm();
      setRestoreError(
        describeBackupFailure(error, "That backup could not be restored."),
      );
    }
  };

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
          <DatabaseBackup className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="font-display text-lg tracking-wide text-fg">
            Backup &amp; restore
          </h2>
          <p className="mt-0.5 text-sm text-muted">
            Take a copy of this server&apos;s database, or put one back.
          </p>
        </div>
      </div>

      {restorePending ? (
        <PendingRestoreBanner
          onCancel={() => cancelRestore.mutate()}
          cancelling={cancelRestore.isPending}
        />
      ) : null}

      <div className="space-y-6">
        <div>
          <SectionHeading>Export</SectionHeading>
          <div className="rounded-xl border border-border/40 bg-white/[0.02] p-4">
            <p className="text-sm text-fg/90">
              Downloads this server&apos;s whole database as one SQLite file:
              every account, every profile, followed series, reading progress,
              bookmarks and collections, as they are right now.
            </p>
            <p className="mt-2 text-xs text-muted">
              The file contains every account on this instance, so keep it
              somewhere private. Nothing on the server changes when you export.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button onClick={runExport} disabled={exportBackup.isPending}>
                <Download className="size-4" aria-hidden />
                {exportBackup.isPending ? "Preparing…" : "Export backup"}
              </Button>
              {exportedName ? (
                <p className="text-sm text-muted">Saved {exportedName}</p>
              ) : null}
            </div>
            {exportError ? (
              <div className="mt-3">
                <Alert tone="danger">{exportError}</Alert>
              </div>
            ) : null}
          </div>
        </div>

        <div>
          <SectionHeading>Restore</SectionHeading>
          <div className="rounded-xl border border-danger/25 bg-danger/[0.04] p-4">
            <p className="text-sm text-fg/90">
              Restoring <strong className="font-semibold">replaces</strong> this
              server&apos;s entire database with the file you upload. Nothing is
              merged, and nothing is limited to your profile or your account —
              every account, every profile and all of their reading data come
              from the backup instead.
            </p>
            <p className="mt-2 text-sm text-fg/90">
              It does not happen immediately. The upload is checked and staged,
              then swapped in the next time the ManhwaManiacs server restarts.
              Until then nothing changes and you can cancel it from here.
            </p>

            <input
              ref={fileInputRef}
              type="file"
              accept=".db"
              className="sr-only"
              onChange={chooseFile}
              aria-label="Backup file to restore"
            />

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button
                variant="secondary"
                onClick={() => fileInputRef.current?.click()}
              >
                <FileUp className="size-4" aria-hidden />
                Choose backup file
              </Button>
              {selectedFile ? (
                <>
                  <p className="min-w-0 truncate text-sm text-muted">
                    {selectedFile.name} · {formatBytes(selectedFile.size)}
                  </p>
                  <Button variant="danger" onClick={openConfirm}>
                    Restore from this file…
                  </Button>
                </>
              ) : (
                <p className="text-sm text-muted">
                  No file chosen. Nothing is uploaded until you confirm.
                </p>
              )}
            </div>

            {restoreError ? (
              <div className="mt-3">
                <Alert tone="danger">{restoreError}</Alert>
              </div>
            ) : null}
            {stagedMessage ? (
              <div className="mt-3">
                <Alert tone="warning">{stagedMessage}</Alert>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={closeConfirm}
        title={selectedFile ? `Restore from “${selectedFile.name}”?` : "Restore backup?"}
      >
        <div className="space-y-4">
          <Alert tone="danger" announce={false}>
            <ul className="list-disc space-y-1.5 pl-4">
              <li>
                Replaces the entire database for this server — every account, not
                just yours; every profile, not just this one.
              </li>
              <li>
                Sign-ins come from the backup too. After the restart, use the
                password each account had when the backup was taken.
              </li>
              <li>
                Applies on the next server restart, not now. Until then the
                staged restore can be cancelled from this page.
              </li>
              <li>
                Nothing currently on this instance is kept. Export a fresh backup
                first if you might want today&apos;s data back.
              </li>
            </ul>
          </Alert>

          <label className="block text-sm">
            <span className="text-fg/90">
              Type <strong className="font-semibold">{RESTORE_CONFIRMATION_PHRASE}</strong>{" "}
              to confirm.
            </span>
            <Input
              className="mt-2"
              value={confirmText}
              onChange={(event) => setConfirmText(event.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </label>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={closeConfirm}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={confirmRestore}
              disabled={!isRestoreConfirmed(confirmText) || importBackup.isPending}
            >
              {importBackup.isPending ? "Uploading…" : "Restore"}
            </Button>
          </div>
        </div>
      </Dialog>
    </section>
  );
}
