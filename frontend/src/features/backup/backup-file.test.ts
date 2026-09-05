import { describe, expect, it } from "vitest";
import { ApiError } from "@/types/api";
import {
  backupDownloadFilename,
  describeBackupFailure,
  isRestoreConfirmed,
  parseContentDispositionFilename,
  RESTORE_CONFIRMATION_PHRASE,
  validateBackupSelection,
} from "./backup-file";

describe("parseContentDispositionFilename", () => {
  it("reads the name FileResponse sends for an export", () => {
    expect(
      parseContentDispositionFilename(
        'attachment; filename="manhwamaniacs-backup-20260905-013000.db"',
      ),
    ).toBe("manhwamaniacs-backup-20260905-013000.db");
  });

  it("reads an unquoted filename", () => {
    expect(
      parseContentDispositionFilename("attachment; filename=backup.db"),
    ).toBe("backup.db");
  });

  it("prefers the RFC 5987 encoded form and decodes it", () => {
    expect(
      parseContentDispositionFilename(
        "attachment; filename=\"fallback.db\"; filename*=UTF-8''man%C3%A9-backup.db",
      ),
    ).toBe("mané-backup.db");
  });

  it("falls back to the plain filename when the encoded one is malformed", () => {
    expect(
      parseContentDispositionFilename(
        "attachment; filename=\"fallback.db\"; filename*=UTF-8''bad%ZZname",
      ),
    ).toBe("fallback.db");
  });

  it("keeps only the last path segment, so a header cannot name a directory", () => {
    expect(
      parseContentDispositionFilename('attachment; filename="../../etc/passwd"'),
    ).toBe("passwd");
    expect(
      parseContentDispositionFilename(
        'attachment; filename="C:\\\\Windows\\\\evil.db"',
      ),
    ).toBe("evil.db");
  });

  it("rejects a header that names nothing usable", () => {
    expect(parseContentDispositionFilename('attachment; filename=""')).toBeNull();
    expect(parseContentDispositionFilename('attachment; filename="."')).toBeNull();
    expect(parseContentDispositionFilename("attachment")).toBeNull();
    expect(parseContentDispositionFilename(null)).toBeNull();
  });
});

describe("backupDownloadFilename", () => {
  const now = new Date(2026, 8, 5, 1, 30, 9);

  it("saves under the name the server chose", () => {
    expect(
      backupDownloadFilename(
        'attachment; filename="manhwamaniacs-backup-20260101-000000.db"',
        now,
      ),
    ).toBe("manhwamaniacs-backup-20260101-000000.db");
  });

  it("stamps its own name, in the backend's format, when the header is missing", () => {
    expect(backupDownloadFilename(null, now)).toBe(
      "manhwamaniacs-backup-20260905-013009.db",
    );
  });
});

describe("validateBackupSelection", () => {
  it("accepts an exported backup", () => {
    expect(
      validateBackupSelection({
        name: "manhwamaniacs-backup-20260905-013000.db",
        size: 262_144,
      }),
    ).toEqual({ ok: true });
  });

  it("accepts an upper-case extension", () => {
    expect(validateBackupSelection({ name: "BACKUP.DB", size: 10 }).ok).toBe(true);
  });

  it("names the file it is refusing when the extension is wrong", () => {
    const check = validateBackupSelection({ name: "holiday.jpg", size: 900 });
    expect(check.ok).toBe(false);
    expect(check.ok === false && check.message).toContain("holiday.jpg");
  });

  it("refuses an empty file rather than uploading zero bytes", () => {
    const check = validateBackupSelection({ name: "backup.db", size: 0 });
    expect(check.ok).toBe(false);
    expect(check.ok === false && check.message).toContain("empty");
  });
});

describe("isRestoreConfirmed", () => {
  it("accepts the phrase, trimmed and in any case", () => {
    expect(isRestoreConfirmed(RESTORE_CONFIRMATION_PHRASE)).toBe(true);
    expect(isRestoreConfirmed("  restore ")).toBe(true);
  });

  it("rejects anything a stray click or a partial word produces", () => {
    expect(isRestoreConfirmed("")).toBe(false);
    expect(isRestoreConfirmed("   ")).toBe(false);
    expect(isRestoreConfirmed("resto")).toBe(false);
    expect(isRestoreConfirmed("restore now")).toBe(false);
  });
});

describe("describeBackupFailure", () => {
  it("shows the server's own reason a file was rejected", () => {
    const error = new ApiError(422, {
      code: "invalid_backup_file",
      message:
        "That file doesn't look like a ManhwaManiacs backup (missing tables: users).",
    });
    expect(describeBackupFailure(error, "Restore failed.")).toBe(
      "That file doesn't look like a ManhwaManiacs backup (missing tables: users).",
    );
  });

  it("passes through the 403 a non-admin gets, unchanged", () => {
    const error = new ApiError(403, {
      code: "forbidden",
      message: "Administrator access required.",
    });
    expect(describeBackupFailure(error, "Restore failed.")).toBe(
      "Administrator access required.",
    );
  });

  it("keeps the transport message when the request never reached the server", () => {
    const error = new ApiError(0, {
      code: "network_error",
      message: "Can't reach ManhwaManiacs right now. Check your connection and try again.",
    });
    expect(describeBackupFailure(error, "Restore failed.")).toContain(
      "Can't reach ManhwaManiacs",
    );
  });

  it("adds the status when the response never used the app's error envelope", () => {
    // A proxy's own 413/502 page: no {code, message}, so `ApiError` has only
    // "Request failed with status …", which tells the user nothing.
    expect(describeBackupFailure(new ApiError(413, {}), "Restore failed.")).toBe(
      "Restore failed. (HTTP 413)",
    );
  });

  it("falls back for anything that is not an ApiError", () => {
    expect(describeBackupFailure(new TypeError("boom"), "Restore failed.")).toBe(
      "Restore failed.",
    );
  });
});
