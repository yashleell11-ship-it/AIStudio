import { describe, expect, it } from "vitest";
import {
  MATURE_TOGGLE_NO_PROFILE_REASON,
  matureToggleBlockReason,
} from "./mature-gate";

describe("matureToggleBlockReason", () => {
  it("allows the write when a profile is active", () => {
    expect(matureToggleBlockReason(3)).toBeNull();
  });

  it("blocks the write with no active profile", () => {
    // PUT /settings retargets the instance-wide default when no X-Profile-Id
    // is attached, so a profile-less write changes every profile's fallback
    // instead of the caller's own setting.
    expect(matureToggleBlockReason(null)).toBe(MATURE_TOGGLE_NO_PROFILE_REASON);
  });

  it("treats profile id 0 as an active profile, not as absent", () => {
    expect(matureToggleBlockReason(0)).toBeNull();
  });
});
