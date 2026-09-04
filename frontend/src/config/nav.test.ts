import { describe, expect, it } from "vitest";
import { moreSections } from "./more-nav";
import {
  isRoleVisibleNavItem,
  moreNav,
  navSections,
  primaryNav,
  secondaryNav,
} from "./nav";

const NON_ADMIN = false;
const ADMIN = true;

function visibleHrefs(
  items: { href: string; adminOnly?: boolean }[],
  isAdmin: boolean,
): string[] {
  return items
    .filter((item) => isRoleVisibleNavItem(item, isAdmin))
    .map((item) => item.href);
}

const allMoreItems = moreSections.flatMap((section) => section.items);

describe("isRoleVisibleNavItem", () => {
  it("shows an unmarked entry to every account", () => {
    expect(isRoleVisibleNavItem({}, NON_ADMIN)).toBe(true);
  });

  it("hides an adminOnly entry from a non-admin", () => {
    expect(isRoleVisibleNavItem({ adminOnly: true }, NON_ADMIN)).toBe(false);
  });

  it("shows an adminOnly entry to an admin", () => {
    expect(isRoleVisibleNavItem({ adminOnly: true }, ADMIN)).toBe(true);
  });

  it("treats adminOnly: false as unmarked", () => {
    expect(isRoleVisibleNavItem({ adminOnly: false }, NON_ADMIN)).toBe(true);
  });
});

describe("preferences are reachable without admin", () => {
  // Registration is open in production, so every account but the owner's is a
  // non-admin. Both surfaces used to mark /settings adminOnly and filter it
  // out, which left those accounts with no route to a theme, a design preset,
  // reader defaults or the 18+ toggle.
  it("keeps /settings in the sidebar footer for a non-admin", () => {
    expect(visibleHrefs(secondaryNav, NON_ADMIN)).toContain("/settings");
  });

  it("keeps /settings in the /more hub for a non-admin", () => {
    expect(visibleHrefs(allMoreItems, NON_ADMIN)).toContain("/settings");
  });

  it("agrees between the two surfaces on every shared destination", () => {
    // The bug was a disagreement, not a single bad flag: an entry hidden in one
    // surface and shown in the other is how a route goes missing.
    const sidebar = new Map(
      [...navSections.flatMap((s) => s.items), ...secondaryNav].map((item) => [
        item.href,
        Boolean(item.adminOnly),
      ]),
    );
    for (const item of allMoreItems) {
      const inSidebar = sidebar.get(item.href);
      if (inSidebar === undefined) continue;
      expect([item.href, Boolean(item.adminOnly)]).toEqual([
        item.href,
        inSidebar,
      ]);
    }
  });

  it("marks nothing else adminOnly than the routes that administer the server", () => {
    const gated = [
      ...primaryNav,
      ...moreNav,
      ...secondaryNav,
      ...allMoreItems,
    ]
      .filter((item) => item.adminOnly)
      .map((item) => item.href);
    expect([...new Set(gated)]).toEqual(["/admin/status"]);
  });
});

describe("server administration stays admin-only", () => {
  it("hides /admin/status from a non-admin in both surfaces", () => {
    expect(visibleHrefs(secondaryNav, NON_ADMIN)).not.toContain("/admin/status");
    expect(visibleHrefs(allMoreItems, NON_ADMIN)).not.toContain("/admin/status");
  });

  it("shows /admin/status to an admin in both surfaces", () => {
    expect(visibleHrefs(secondaryNav, ADMIN)).toContain("/admin/status");
    expect(visibleHrefs(allMoreItems, ADMIN)).toContain("/admin/status");
  });
});
