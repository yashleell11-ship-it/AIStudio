import { describe, expect, it } from "vitest";
import { ApiError } from "@/types/api";
import {
  describeRegisterError,
  isAuthQueryKey,
  isPublicAuthPath,
  isUnauthorizedError,
  resolveLoginScreenMode,
  resolveRegisterAvailability,
  shouldShowInviteField,
} from "./access";
import type { BootstrapStatus } from "./types";

function status(overrides: Partial<BootstrapStatus> = {}): BootstrapStatus {
  return { needs_bootstrap: false, registration_enabled: true, ...overrides };
}

describe("isPublicAuthPath", () => {
  it("matches the auth routes exactly", () => {
    expect(isPublicAuthPath("/login")).toBe(true);
    expect(isPublicAuthPath("/register")).toBe(true);
  });

  it("does not match protected routes or lookalikes", () => {
    expect(isPublicAuthPath("/")).toBe(false);
    expect(isPublicAuthPath("/library")).toBe(false);
    expect(isPublicAuthPath("/login/extra")).toBe(false);
    expect(isPublicAuthPath("/settings")).toBe(false);
  });
});

describe("isUnauthorizedError", () => {
  it("is true only for an ApiError with status 401", () => {
    expect(isUnauthorizedError(new ApiError(401, { code: "not_authenticated" }))).toBe(true);
  });

  it("is false for other statuses and non-ApiError values", () => {
    expect(isUnauthorizedError(new ApiError(403, { code: "forbidden" }))).toBe(false);
    expect(isUnauthorizedError(new ApiError(500, { code: "server_error" }))).toBe(false);
    expect(isUnauthorizedError(new Error("boom"))).toBe(false);
    expect(isUnauthorizedError(null)).toBe(false);
    expect(isUnauthorizedError(undefined)).toBe(false);
  });
});

describe("isAuthQueryKey", () => {
  it("matches keys in the auth namespace so the 401 handler skips them", () => {
    expect(isAuthQueryKey(["auth", "me"])).toBe(true);
    expect(isAuthQueryKey(["auth", "bootstrap"])).toBe(true);
  });

  it("does not match other feature keys", () => {
    expect(isAuthQueryKey(["downloads"])).toBe(false);
    expect(isAuthQueryKey(["library", "series", 1])).toBe(false);
    expect(isAuthQueryKey([])).toBe(false);
  });
});

describe("resolveLoginScreenMode", () => {
  it("shows the bootstrap form when the instance has no account yet (older backend, no bootstrap_open field)", () => {
    expect(resolveLoginScreenMode(status({ needs_bootstrap: true }))).toBe("bootstrap");
  });

  it("shows the login form once an account exists", () => {
    expect(resolveLoginScreenMode(status({ needs_bootstrap: false }))).toBe("login");
  });

  it("falls back to the ordinary sign-in form once the takeover window has expired", () => {
    // Zero users, but bootstrap_open says the window closed: this is no
    // longer an uninvited claim-the-instance moment.
    expect(
      resolveLoginScreenMode(status({ needs_bootstrap: true, bootstrap_open: false })),
    ).toBe("login");
  });

  it("honours an explicit bootstrap_open: true", () => {
    expect(resolveLoginScreenMode(status({ bootstrap_open: true }))).toBe("bootstrap");
  });
});

describe("resolveRegisterAvailability", () => {
  it("is bootstrap when no account exists (older backend, no bootstrap_open field)", () => {
    expect(
      resolveRegisterAvailability(status({ needs_bootstrap: true, registration_enabled: false })),
    ).toBe("bootstrap");
  });

  it("is open when accounts exist and self-registration is enabled", () => {
    expect(
      resolveRegisterAvailability(status({ needs_bootstrap: false, registration_enabled: true })),
    ).toBe("open");
  });

  it("is closed when accounts exist and self-registration is disabled", () => {
    expect(
      resolveRegisterAvailability(status({ needs_bootstrap: false, registration_enabled: false })),
    ).toBe("closed");
  });

  it("is open (not bootstrap) once the takeover window has expired, when registration is still enabled", () => {
    expect(
      resolveRegisterAvailability(
        status({ needs_bootstrap: true, bootstrap_open: false, registration_enabled: true }),
      ),
    ).toBe("open");
  });

  it("is closed once the takeover window has expired and registration is disabled — the instance is stuck until an admin re-arms it", () => {
    expect(
      resolveRegisterAvailability(
        status({ needs_bootstrap: true, bootstrap_open: false, registration_enabled: false }),
      ),
    ).toBe("closed");
  });

  it("prefers the explicit registration_open flag over registration_enabled", () => {
    expect(
      resolveRegisterAvailability(
        status({ needs_bootstrap: false, registration_enabled: false, registration_open: true }),
      ),
    ).toBe("open");
    expect(
      resolveRegisterAvailability(
        status({ needs_bootstrap: false, registration_enabled: true, registration_open: false }),
      ),
    ).toBe("closed");
  });
});

describe("shouldShowInviteField", () => {
  it("shows the field once registration is open and the server requires a code", () => {
    expect(shouldShowInviteField(status({ invite_code_required: true }))).toBe(true);
  });

  it("hides the field when the server says no code is required", () => {
    expect(shouldShowInviteField(status({ invite_code_required: false }))).toBe(false);
  });

  it("treats an absent flag as not required (older/not-yet-landed backend)", () => {
    expect(shouldShowInviteField(status())).toBe(false);
  });

  it("never shows during bootstrap, even if the flag is somehow true", () => {
    expect(
      shouldShowInviteField(status({ needs_bootstrap: true, invite_code_required: true })),
    ).toBe(false);
  });

  it("never shows when registration is closed", () => {
    expect(
      shouldShowInviteField(
        status({ registration_enabled: false, invite_code_required: true }),
      ),
    ).toBe(false);
  });
});

describe("describeRegisterError", () => {
  it("gives plain wording for a missing invite code", () => {
    expect(
      describeRegisterError(new ApiError(403, { code: "invite_code_required", message: "x" })),
    ).toBe("An invite code is required to create an account on this instance.");
  });

  it("gives plain wording for a wrong invite code", () => {
    expect(
      describeRegisterError(new ApiError(403, { code: "invite_code_invalid", message: "x" })),
    ).toBe("That invite code isn't valid. Check it and try again.");
  });

  it("explains registration being disabled entirely", () => {
    expect(
      describeRegisterError(new ApiError(403, { code: "registration_disabled", message: "x" })),
    ).toBe("Registration is currently closed on this instance.");
  });

  it("explains a duplicate username", () => {
    expect(
      describeRegisterError(new ApiError(409, { code: "username_taken", message: "x" })),
    ).toBe("That username is already taken.");
  });

  it("explains rate limiting", () => {
    expect(
      describeRegisterError(new ApiError(429, { code: "rate_limited", message: "x" })),
    ).toBe("Too many attempts. Wait a moment and try again.");
  });

  it("falls back to the server's own message for anything not special-cased", () => {
    expect(
      describeRegisterError(
        new ApiError(422, { code: "weak_password", message: "Password is too short." }),
      ),
    ).toBe("Password is too short.");
  });

  it("gives a generic message for a non-ApiError failure", () => {
    expect(describeRegisterError(new Error("boom"))).toBe(
      "Could not create the account. Please try again.",
    );
    expect(describeRegisterError(null)).toBe(
      "Could not create the account. Please try again.",
    );
  });
});
