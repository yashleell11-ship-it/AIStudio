import { describe, expect, it } from "vitest";
import {
  PROFILE_PICKER_PATH,
  isPickerPath,
  shouldRedirectToPicker,
  type ProfileGateInput,
} from "./access";

function gate(overrides: Partial<ProfileGateInput> = {}): ProfileGateInput {
  return {
    authenticated: true,
    hydrated: true,
    hasActiveProfile: false,
    pathname: "/library",
    ...overrides,
  };
}

describe("isPickerPath", () => {
  it("matches the picker route exactly", () => {
    expect(isPickerPath(PROFILE_PICKER_PATH)).toBe(true);
    expect(isPickerPath("/profiles")).toBe(true);
  });

  it("does not match the management page or other routes", () => {
    expect(isPickerPath("/profiles/manage")).toBe(false);
    expect(isPickerPath("/")).toBe(false);
    expect(isPickerPath("/library")).toBe(false);
  });
});

describe("shouldRedirectToPicker", () => {
  it("redirects a signed-in, hydrated visitor with no active profile", () => {
    expect(shouldRedirectToPicker(gate())).toBe(true);
  });

  it("does not redirect before auth resolves", () => {
    expect(shouldRedirectToPicker(gate({ authenticated: false }))).toBe(false);
  });

  it("does not redirect before the persisted selection hydrates", () => {
    // The critical case: never bounce to the picker before restoring the
    // remembered profile on a reload.
    expect(shouldRedirectToPicker(gate({ hydrated: false }))).toBe(false);
  });

  it("does not redirect once a profile is active", () => {
    expect(shouldRedirectToPicker(gate({ hasActiveProfile: true }))).toBe(false);
  });

  it("does not redirect when already on the picker (no loop)", () => {
    expect(shouldRedirectToPicker(gate({ pathname: PROFILE_PICKER_PATH }))).toBe(false);
  });

  it("still redirects to the picker from the management page without a profile", () => {
    expect(shouldRedirectToPicker(gate({ pathname: "/profiles/manage" }))).toBe(true);
  });
});
