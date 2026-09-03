import { describe, expect, it } from "vitest";
import {
  LIBRARY_DISCOVERY_QUERY_ROOT,
  LIBRARY_QUERY_ROOT,
} from "@/features/library/hooks";
import { SOURCES_QUERY_ROOT } from "@/features/sources/hooks";
import {
  MATURE_GATED_QUERY_ROOTS,
  MATURE_TOGGLE_NO_PROFILE_REASON,
  invalidateMatureGatedQueries,
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

describe("invalidateMatureGatedQueries", () => {
  function recorder() {
    const roots: unknown[] = [];
    return {
      roots,
      invalidateQueries: ({ queryKey }: { queryKey: readonly unknown[] }) => {
        roots.push(queryKey[0]);
      },
    };
  }

  it("drops every cache the backend filters by the 18+ gate", () => {
    const client = recorder();
    invalidateMatureGatedQueries(client);
    // `list_series` (and therefore the library grid, the followed index and
    // library search), `continue_reading` and `recommendations` all go through
    // `FollowedSeriesService._visible`, so both library roots have to go.
    expect(client.roots).toContain(LIBRARY_QUERY_ROOT);
    expect(client.roots).toContain(LIBRARY_DISCOVERY_QUERY_ROOT);
    expect(client.roots).toContain(SOURCES_QUERY_ROOT);
    expect(client.roots).toContain("preferences");
  });

  it("names no root that nothing is cached under", () => {
    // `intelligence` was the discovery root before the source-native rewrite
    // renamed it; invalidating it matched nothing and left the gated library
    // caches in place.
    expect(MATURE_GATED_QUERY_ROOTS).not.toContain("intelligence");
  });
});
