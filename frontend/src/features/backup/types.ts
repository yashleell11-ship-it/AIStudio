/**
 * Database backup and restore (`backend/routes/backup.py`).
 *
 * One instance-wide SQLite file, not a per-profile or per-account export: the
 * backend snapshots the whole database with `VACUUM INTO` and, on import,
 * replaces that same file. Admin-only on the server for exactly that reason.
 */

/** `GET /backup/status` — is a validated restore waiting for the next start? */
export interface BackupStatus {
  restore_pending: boolean;
}

/** `POST /backup/import` — the upload was accepted and staged, not applied. */
export interface RestoreStaged {
  status: string;
  message: string;
}
