import { describe, expect, it } from "vitest";
import { ApiError } from "@/types/api";
import {
  activeToggleLabel,
  deleteMemberConfirmation,
  describeMembersFailure,
  describeOtherMembers,
  formatSessionCount,
  memberRowGuard,
  SELF_ROW_REASON,
  shapeMemberRows,
} from "./members";
import type { MemberAccount } from "./types";

const OWNER_ID = 1;

function member(overrides: Partial<MemberAccount> = {}): MemberAccount {
  return {
    id: 2,
    username: "friend",
    is_admin: false,
    is_active: true,
    created_at: "2026-09-02 10:00:00",
    last_login_at: null,
    session_count: 0,
    ...overrides,
  };
}

describe("shapeMemberRows", () => {
  it("puts the caller's own account first, whatever order the API used", () => {
    const rows = shapeMemberRows(
      [
        member({ id: 3, created_at: "2026-08-01 00:00:00" }),
        member({ id: OWNER_ID, username: "owner", created_at: "2026-09-05 00:00:00" }),
        member({ id: 2, created_at: "2026-08-15 00:00:00" }),
      ],
      OWNER_ID,
    );
    expect(rows.map((row) => row.member.id)).toEqual([OWNER_ID, 3, 2]);
  });

  it("marks exactly one row as self", () => {
    const rows = shapeMemberRows([member({ id: 2 }), member({ id: OWNER_ID })], OWNER_ID);
    expect(rows.map((row) => row.isSelf)).toEqual([true, false]);
  });

  it("orders everyone else by when they joined, oldest first", () => {
    // "Who signed up?" is the question; the newest name belongs at the bottom.
    const rows = shapeMemberRows(
      [
        member({ id: 5, created_at: "2026-09-06 08:00:00" }),
        member({ id: 4, created_at: "2026-09-04 08:00:00" }),
        member({ id: 6, created_at: "2026-09-05 08:00:00" }),
      ],
      OWNER_ID,
    );
    expect(rows.map((row) => row.member.id)).toEqual([4, 6, 5]);
  });

  it("reads the backend's naive-UTC timestamps as UTC when ordering", () => {
    // A `Z`-less string and a `Z` one for the same instant must not be split
    // by the viewer's offset. parseUtcTimestamp handles that; this pins it.
    const rows = shapeMemberRows(
      [
        member({ id: 7, created_at: "2026-09-04T09:00:00Z" }),
        member({ id: 8, created_at: "2026-09-04 08:59:59" }),
      ],
      OWNER_ID,
    );
    expect(rows.map((row) => row.member.id)).toEqual([8, 7]);
  });

  it("falls back to id when two accounts joined in the same second", () => {
    const rows = shapeMemberRows(
      [member({ id: 12 }), member({ id: 11 })],
      OWNER_ID,
    );
    expect(rows.map((row) => row.member.id)).toEqual([11, 12]);
  });

  it("marks nobody as self while the caller's id is still unknown", () => {
    for (const unknown of [null, undefined]) {
      const rows = shapeMemberRows([member({ id: 2 }), member({ id: 3 })], unknown);
      expect(rows.every((row) => !row.isSelf)).toBe(true);
    }
  });

  it("does not mutate the cached array react-query handed it", () => {
    const input = [member({ id: 2 }), member({ id: OWNER_ID })];
    shapeMemberRows(input, OWNER_ID);
    expect(input.map((row) => row.id)).toEqual([2, OWNER_ID]);
  });
});

describe("memberRowGuard", () => {
  it("lets an admin act on any other account", () => {
    expect(memberRowGuard(member({ id: 2 }), OWNER_ID)).toEqual({
      isSelf: false,
      canToggleActive: true,
      canDelete: true,
      reason: null,
    });
  });

  it("locks both controls on the caller's own row, and says why", () => {
    // The server answers 400 to an admin targeting themselves; the buttons
    // should say so before the click, not after it.
    expect(memberRowGuard(member({ id: OWNER_ID }), OWNER_ID)).toEqual({
      isSelf: true,
      canToggleActive: false,
      canDelete: false,
      reason: SELF_ROW_REASON,
    });
  });

  it("never treats a row as self while the caller's id is unknown", () => {
    // `/auth/me` not answered yet: no row is self. The panel does not render
    // until `is_admin` is known, which arrives with the id, so this is a
    // belt-and-braces case rather than a reachable one.
    expect(memberRowGuard(member({ id: 2 }), null).isSelf).toBe(false);
    expect(memberRowGuard(member({ id: 2 }), undefined).isSelf).toBe(false);
  });

  it("guards on id alone, so a username collision cannot unlock the row", () => {
    expect(memberRowGuard(member({ id: 9, username: "owner" }), OWNER_ID).canDelete).toBe(true);
  });
});

describe("activeToggleLabel", () => {
  it("names the action, not the state", () => {
    expect(activeToggleLabel(true)).toBe("Deactivate");
    expect(activeToggleLabel(false)).toBe("Reactivate");
  });
});

describe("deleteMemberConfirmation", () => {
  it("names the account in the title, the body and the confirm button", () => {
    const copy = deleteMemberConfirmation(member({ username: "alice" }));
    expect(copy.title).toBe("Delete alice?");
    expect(copy.body).toContain("alice's account");
    expect(copy.action).toBe("Delete alice");
  });

  it("spells out that everything the account owns goes with it", () => {
    const { body } = deleteMemberConfirmation(member({ username: "alice" }));
    for (const owned of ["profile", "followed series", "reading progress", "bookmarks", "collections", "sessions"]) {
      expect(body).toContain(owned);
    }
    expect(body).toContain("no undo");
  });

  it("uses the username verbatim, so an odd name still reads as itself", () => {
    const copy = deleteMemberConfirmation(member({ username: "Ünïcode_42" }));
    expect(copy.title).toBe("Delete Ünïcode_42?");
  });
});

describe("formatSessionCount", () => {
  it("pluralises correctly and never prints '0 sessions'", () => {
    expect(formatSessionCount(0)).toBe("No sessions");
    expect(formatSessionCount(1)).toBe("1 session");
    expect(formatSessionCount(4)).toBe("4 sessions");
  });

  it("treats a negative count from a confused backend as none", () => {
    expect(formatSessionCount(-1)).toBe("No sessions");
  });
});

describe("describeOtherMembers", () => {
  it("says so when the owner is alone", () => {
    const rows = shapeMemberRows([member({ id: OWNER_ID })], OWNER_ID);
    expect(describeOtherMembers(rows)).toBe(
      "Only your account so far. Anyone who registers appears here.",
    );
  });

  it("counts everyone but the caller", () => {
    expect(
      describeOtherMembers(
        shapeMemberRows([member({ id: OWNER_ID }), member({ id: 2 })], OWNER_ID),
      ),
    ).toBe("1 other account.");
    expect(
      describeOtherMembers(
        shapeMemberRows(
          [member({ id: OWNER_ID }), member({ id: 2 }), member({ id: 3 })],
          OWNER_ID,
        ),
      ),
    ).toBe("2 other accounts.");
  });
});

describe("describeMembersFailure", () => {
  it("repeats the server's own wording, including the self-target 400", () => {
    const error = new ApiError(400, {
      code: "cannot_modify_self",
      message: "You cannot deactivate your own account.",
    });
    expect(describeMembersFailure(error, "fallback")).toBe(
      "You cannot deactivate your own account.",
    );
  });

  it("passes the http client's own network message through", () => {
    const error = new ApiError(0, {
      code: "network_error",
      message: "Can't reach ManhwaManiacs right now.",
    });
    expect(describeMembersFailure(error, "fallback")).toBe(
      "Can't reach ManhwaManiacs right now.",
    );
  });

  it("adds the status when the response never carried the app's envelope", () => {
    // A proxy's 502 arrives with `code: unknown_error` and a message that is
    // only the status text — not something to show as if the app said it.
    const error = new ApiError(502, { message: "Bad Gateway" });
    expect(describeMembersFailure(error, "Could not load the member list.")).toBe(
      "Could not load the member list. (HTTP 502)",
    );
  });

  it("falls back for anything that is not an ApiError", () => {
    expect(describeMembersFailure(new Error("boom"), "fallback")).toBe("fallback");
    expect(describeMembersFailure(undefined, "fallback")).toBe("fallback");
  });
});
