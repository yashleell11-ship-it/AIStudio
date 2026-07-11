import { describe, expect, it } from "vitest";
import { ApiError } from "@/types/api";
import {
  isAuthQueryKey,
  isPublicAuthPath,
  isUnauthorizedError,
  resolveLoginScreenMode,
  resolveRegisterAvailability,
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
  it("shows the bootstrap form when the instance has no account yet", () => {
    expect(resolveLoginScreenMode(status({ needs_bootstrap: true }))).toBe("bootstrap");
  });

  it("shows the login form once an account exists", () => {
    expect(resolveLoginScreenMode(status({ needs_bootstrap: false }))).toBe("login");
  });
});

describe("resolveRegisterAvailability", () => {
  it("is bootstrap when no account exists (regardless of the registration flag)", () => {
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
});
