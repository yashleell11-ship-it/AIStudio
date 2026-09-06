import { describe, expect, it, vi } from "vitest";
import { isAuthQueryKey } from "@/features/auth/access";
import { NOT_MATURE_GATED_QUERY_ROOTS } from "@/features/preferences/mature-gate";
import { MEMBERS_QUERY_KEY } from "./hooks";

// `hooks` pulls in the fetch helper through `./api`; nothing here sends a
// request, so the helper is stubbed rather than loaded with its config.
vi.mock("@/services/http", () => ({
  http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

describe("MEMBERS_QUERY_KEY", () => {
  it("lives under the auth namespace, which the 401 handler skips on purpose", () => {
    // The consequence is that `useMembers` must report an expired session
    // itself — the comment on the key says why; this pins that the key is
    // where that comment says it is.
    expect(isAuthQueryKey(MEMBERS_QUERY_KEY)).toBe(true);
    expect(MEMBERS_QUERY_KEY).toEqual(["auth", "users"]);
  });

  it("sits under a root the 18+ gate is known not to filter", () => {
    // Accounts are not series content. Giving this list its own root would
    // trip the drift check in mature-gate.test.ts until someone classified it;
    // reusing `auth` inherits the classification it already has.
    expect(NOT_MATURE_GATED_QUERY_ROOTS).toContain(MEMBERS_QUERY_KEY[0]);
  });
});
