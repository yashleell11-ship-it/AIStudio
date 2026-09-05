/**
 * Naming a downloaded backup, checking a chosen one, and wording a failure.
 *
 * Pure on purpose — no DOM, no fetch — so the rules that guard the single most
 * destructive action in the product are testable directly (vitest runs
 * `src/**\/*.test.ts` under node, with no React testing library).
 */

import { ApiError } from "@/types/api";

/** Mirrors `backup_service.backup_filename()`. */
const FILENAME_PREFIX = "manhwamaniacs-backup-";
const BACKUP_EXTENSION = ".db";

/**
 * The word a restore has to be confirmed with.
 *
 * A destructive action one stray click away from a `Restore` button is a
 * destructive action that eventually happens by accident, so the confirm button
 * stays disabled until this is typed. Matching is trimmed and case-insensitive:
 * the point is deliberate intent, and no amount of stray clicking types a word.
 */
export const RESTORE_CONFIRMATION_PHRASE = "RESTORE";

export function isRestoreConfirmed(input: string): boolean {
  return input.trim().toUpperCase() === RESTORE_CONFIRMATION_PHRASE;
}

/** The result of checking a file the user picked, before anything is uploaded. */
export type BackupSelectionCheck =
  | { ok: true }
  | { ok: false; message: string };

/** Two digits, for the local-time stamp in the fallback filename. */
function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/**
 * Strip a `Content-Disposition` filename down to something safe to write to
 * disk: the last path segment only, no separators, no control characters, and
 * nothing that names a directory rather than a file.
 */
function sanitizeFilename(value: string): string | null {
  const lastSegment = value.split(/[\\/]/).pop() ?? "";
  const cleaned = lastSegment.replace(/[\u0000-\u001f\u007f]/g, "").trim();
  if (cleaned === "" || cleaned === "." || cleaned === "..") return null;
  return cleaned;
}

/**
 * The filename the server asked us to save the download as, or null.
 *
 * Prefers RFC 5987's `filename*` when present — it is the encoded form, and a
 * server that sends both sends the plain `filename` only as an ASCII fallback.
 */
export function parseContentDispositionFilename(
  header: string | null | undefined,
): string | null {
  if (!header) return null;

  const extended = /filename\*\s*=\s*[^']*'[^']*'([^;]+)/i.exec(header);
  if (extended) {
    try {
      const decoded = sanitizeFilename(decodeURIComponent(extended[1].trim()));
      if (decoded) return decoded;
    } catch {
      // Malformed percent-encoding: fall through to the plain `filename`.
    }
  }

  const quoted = /filename\s*=\s*"([^"]*)"/i.exec(header);
  if (quoted) return sanitizeFilename(quoted[1]);

  const bare = /filename\s*=\s*([^;]+)/i.exec(header);
  if (bare) return sanitizeFilename(bare[1]);

  return null;
}

/**
 * What to call the exported file. The backend already stamps a name onto the
 * response; `now` only names the file when that header is missing or unusable,
 * so a download is never saved as something opaque like "download".
 */
export function backupDownloadFilename(
  contentDisposition: string | null | undefined,
  now: Date,
): string {
  const fromServer = parseContentDispositionFilename(contentDisposition);
  if (fromServer) return fromServer;

  const stamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `${FILENAME_PREFIX}${stamp}${BACKUP_EXTENSION}`;
}

/**
 * Reject a file that cannot possibly be a backup, before it is uploaded.
 *
 * A courtesy, not the authority: `backup_service._validate_backup_file` opens
 * the upload as SQLite and checks for the tables a real backup has, and that
 * check is the one that decides. This one exists so the common mistakes — the
 * wrong file in the picker, a truncated download — are answered immediately
 * instead of after a round trip.
 */
export function validateBackupSelection(file: {
  name: string;
  size: number;
}): BackupSelectionCheck {
  if (!file.name.toLowerCase().endsWith(BACKUP_EXTENSION)) {
    return {
      ok: false,
      message: `“${file.name}” isn't a ${BACKUP_EXTENSION} file. Choose the backup you exported from ManhwaManiacs.`,
    };
  }
  if (file.size <= 0) {
    return {
      ok: false,
      message: `“${file.name}” is empty. The export may not have finished — take a fresh backup and try again.`,
    };
  }
  return { ok: true };
}

/**
 * What to show the user when a backup call fails.
 *
 * The server words its own failures for a reader — "That file doesn't look like
 * a ManhwaManiacs backup (missing tables: …)" — and it is the only thing that
 * knows why a restore was refused, so its message is passed through verbatim
 * rather than re-written here. `fallback` covers the responses that never went
 * through the app's `{code, message}` envelope at all (a proxy's 413 or 502),
 * where `ApiError` has nothing better than the status to report.
 */
export function describeBackupFailure(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.code !== "unknown_error") return error.message;
    return `${fallback} (HTTP ${error.status})`;
  }
  return fallback;
}
