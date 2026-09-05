import { describe, expect, it } from "vitest";
import { ApiError } from "@/types/api";
import {
  CHANGE_PASSWORD_FIELDS,
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  canSignOutEverywhere,
  describeAuthError,
  describeSessionDevice,
  fieldsToClearAfterFailure,
  sessionRowAction,
  sortSessionsForDisplay,
  toChangePasswordPayload,
  validateChangePassword,
  type ChangePasswordFormValues,
} from "./account-security";
import type { AccountSession } from "./types";

const NEW_PASSWORD = "correct-horse-battery-staple";

function values(overrides: Partial<ChangePasswordFormValues> = {}): ChangePasswordFormValues {
  return {
    currentPassword: "old-donkey-cutlery-clamp",
    newPassword: NEW_PASSWORD,
    confirmPassword: NEW_PASSWORD,
    ...overrides,
  };
}

function session(overrides: Partial<AccountSession> = {}): AccountSession {
  return {
    id: 1,
    created_at: "2026-09-01 10:00:00",
    last_used_at: "2026-09-05 09:00:00",
    expires_at: "2026-10-05 09:00:00",
    user_agent: null,
    ip_address: null,
    current: false,
    ...overrides,
  };
}

describe("validateChangePassword", () => {
  it("accepts a well-formed change", () => {
    expect(validateChangePassword(values())).toBeNull();
  });

  it("asks for the current password before anything else", () => {
    expect(validateChangePassword(values({ currentPassword: "" }))).toBe(
      "Enter your current password.",
    );
  });

  it("asks for a new password when the field is empty", () => {
    expect(
      validateChangePassword(values({ newPassword: "", confirmPassword: "" })),
    ).toBe("Enter a new password.");
  });

  it("mirrors the server's minimum-length wording so the two cannot disagree", () => {
    const short = "a".repeat(MIN_PASSWORD_LENGTH - 1);
    expect(validateChangePassword(values({ newPassword: short, confirmPassword: short }))).toBe(
      `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`,
    );
  });

  it("accepts a password of exactly the minimum length", () => {
    const exact = "a".repeat(MIN_PASSWORD_LENGTH);
    expect(
      validateChangePassword(values({ newPassword: exact, confirmPassword: exact })),
    ).toBeNull();
  });

  it("rejects a password past the server's ceiling", () => {
    const huge = "a".repeat(MAX_PASSWORD_LENGTH + 1);
    expect(validateChangePassword(values({ newPassword: huge, confirmPassword: huge }))).toBe(
      "Password is too long.",
    );
  });

  it("catches a mistyped confirmation", () => {
    expect(validateChangePassword(values({ confirmPassword: `${NEW_PASSWORD}x` }))).toBe(
      "The new passwords don't match.",
    );
  });

  it("refuses a change that changes nothing", () => {
    // A no-op rotation still revokes every other session, so a double paste of
    // the same secret should not go through as if it accomplished something.
    expect(
      validateChangePassword(
        values({ currentPassword: NEW_PASSWORD, newPassword: NEW_PASSWORD }),
      ),
    ).toBe("Your new password must be different from your current one.");
  });
});

describe("toChangePasswordPayload", () => {
  it("builds exactly the body POST /auth/change-password accepts", () => {
    expect(toChangePasswordPayload(values())).toEqual({
      current_password: "old-donkey-cutlery-clamp",
      new_password: NEW_PASSWORD,
    });
  });

  it("never sends the confirmation field to the server", () => {
    expect(Object.keys(toChangePasswordPayload(values()))).toEqual([
      "current_password",
      "new_password",
    ]);
  });
});

describe("fieldsToClearAfterFailure", () => {
  it("clears only the current password when the server says it was wrong", () => {
    const error = new ApiError(401, {
      code: "invalid_credentials",
      message: "Current password is incorrect.",
    });
    expect(fieldsToClearAfterFailure(error)).toEqual(["currentPassword"]);
  });

  it("clears the new password pair when the server rejects its strength", () => {
    const error = new ApiError(422, {
      code: "weak_password",
      message: "Password must be at least 8 characters.",
    });
    expect(fieldsToClearAfterFailure(error)).toEqual(["newPassword", "confirmPassword"]);
  });

  it("clears everything when the failure is not one we recognise", () => {
    expect(fieldsToClearAfterFailure(new Error("boom"))).toEqual([...CHANGE_PASSWORD_FIELDS]);
    expect(
      fieldsToClearAfterFailure(new ApiError(500, { code: "server_error", message: "Oops." })),
    ).toEqual([...CHANGE_PASSWORD_FIELDS]);
  });

  it("never leaves a secret behind that the server actually rejected", () => {
    for (const code of ["invalid_credentials", "weak_password", "rate_limited"]) {
      const cleared = fieldsToClearAfterFailure(new ApiError(400, { code, message: "no" }));
      expect(cleared.length).toBeGreaterThan(0);
    }
  });
});

describe("describeAuthError", () => {
  it("repeats the server's own wording rather than inventing its own", () => {
    // The backend decides how much a failure discloses; re-wording it here
    // could say more about the account than the server chose to.
    const error = new ApiError(401, {
      code: "invalid_credentials",
      message: "Current password is incorrect.",
    });
    expect(describeAuthError(error, "fallback")).toBe("Current password is incorrect.");
  });

  it("falls back only when there is no server message at all", () => {
    expect(describeAuthError(new Error("TypeError: fetch failed"), "fallback")).toBe("fallback");
    expect(describeAuthError(undefined, "fallback")).toBe("fallback");
  });
});

describe("describeSessionDevice", () => {
  it("names the browser and the platform", () => {
    expect(
      describeSessionDevice(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
      ),
    ).toBe("Chrome on Windows");
  });

  it("does not call Chromium browsers Safari", () => {
    expect(
      describeSessionDevice(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
      ),
    ).toBe("Edge on macOS");
  });

  it("recognises real Safari on an iPhone", () => {
    expect(
      describeSessionDevice(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
      ),
    ).toBe("Safari on iPhone");
  });

  it("names the Flutter client, which sends Dart's default agent", () => {
    expect(describeSessionDevice("Dart/3.5 (dart:io)")).toBe("ManhwaManiacs app");
  });

  it("says so plainly when there is nothing to go on", () => {
    expect(describeSessionDevice(null)).toBe("Unknown device");
    expect(describeSessionDevice("   ")).toBe("Unknown device");
    expect(describeSessionDevice("curl/8.9.1")).toBe("Unknown device");
  });
});

describe("sortSessionsForDisplay", () => {
  it("puts this device first even when it is the least recently used", () => {
    const rows = sortSessionsForDisplay([
      session({ id: 2, last_used_at: "2026-09-05 12:00:00" }),
      session({ id: 1, last_used_at: "2026-09-01 08:00:00", current: true }),
      session({ id: 3, last_used_at: "2026-09-05 11:00:00" }),
    ]);
    expect(rows.map((row) => row.id)).toEqual([1, 2, 3]);
  });

  it("orders the rest most recently used first", () => {
    const rows = sortSessionsForDisplay([
      session({ id: 5, last_used_at: "2026-09-02 08:00:00" }),
      session({ id: 6, last_used_at: "2026-09-04 08:00:00" }),
    ]);
    expect(rows.map((row) => row.id)).toEqual([6, 5]);
  });

  it("does not mutate the cached array react-query handed it", () => {
    const input = [session({ id: 1 }), session({ id: 2, current: true })];
    sortSessionsForDisplay(input);
    expect(input.map((row) => row.id)).toEqual([1, 2]);
  });
});

describe("sessionRowAction", () => {
  it("offers a plain revoke for another device", () => {
    expect(sessionRowAction(session({ current: false }))).toBe("revoke");
  });

  it("never offers revoke for this device", () => {
    // DELETE /auth/sessions/{id} accepts the caller's own id: revoking it here
    // would drop this tab into a signed-out app holding a stale cache, with
    // nothing on screen explaining what happened.
    expect(sessionRowAction(session({ current: true }))).toBe("sign-out-current");
  });
});

describe("canSignOutEverywhere", () => {
  it("stays shut until the consequence is acknowledged", () => {
    expect(canSignOutEverywhere(false, false)).toBe(false);
  });

  it("does not fire twice while a request is in flight", () => {
    expect(canSignOutEverywhere(true, true)).toBe(false);
  });

  it("fires once acknowledged and idle", () => {
    expect(canSignOutEverywhere(true, false)).toBe(true);
  });
});
