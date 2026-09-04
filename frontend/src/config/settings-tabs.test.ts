import { describe, expect, it } from "vitest";
import {
  SETTINGS_TABS,
  resolveSettingsTab,
  visibleSettingsTabs,
  type SettingsTabId,
} from "./settings-tabs";

const NON_ADMIN = false;
const ADMIN = true;

function ids(isAdmin: boolean): SettingsTabId[] {
  return visibleSettingsTabs(isAdmin).map((tab) => tab.id);
}

describe("visibleSettingsTabs", () => {
  it("gives a non-admin every per-reader preference", () => {
    expect(ids(NON_ADMIN)).toEqual([
      "design",
      "appearance",
      "reader",
      "content",
      "shortcuts",
    ]);
  });

  it("gives an admin those plus the instance-global panel", () => {
    expect(ids(ADMIN)).toEqual(SETTINGS_TABS.map((tab) => tab.id));
    expect(ids(ADMIN)).toContain("notifications");
  });

  it("withholds the update-checker panel from a non-admin", () => {
    // It writes the singleton UpdateSettings row — one schedule for the whole
    // instance. `PUT /updates/settings` carries require_admin_user, so showing
    // the form would only hand every account a Save that 403s.
    expect(ids(NON_ADMIN)).not.toContain("notifications");
  });

  it("leaves a non-admin a usable page rather than an empty one", () => {
    expect(visibleSettingsTabs(NON_ADMIN).length).toBeGreaterThan(0);
  });

  it("preserves render order", () => {
    const order = SETTINGS_TABS.map((tab) => tab.id);
    for (const isAdmin of [NON_ADMIN, ADMIN]) {
      const seen = ids(isAdmin).map((id) => order.indexOf(id));
      expect(seen).toEqual([...seen].sort((a, b) => a - b));
    }
  });
});

describe("resolveSettingsTab", () => {
  it("honours a per-reader tab for a non-admin", () => {
    expect(resolveSettingsTab("appearance", NON_ADMIN)).toBe("appearance");
  });

  it("refuses to open the admin panel for a non-admin", () => {
    // The click handler cannot reach this state, but `is_admin` arrives from
    // GET /auth/me after first paint and can change under a mounted page.
    expect(resolveSettingsTab("notifications", NON_ADMIN)).toBe("design");
  });

  it("opens the admin panel for an admin", () => {
    expect(resolveSettingsTab("notifications", ADMIN)).toBe("notifications");
  });

  it("always resolves to a tab the account may actually open", () => {
    for (const tab of SETTINGS_TABS) {
      for (const isAdmin of [NON_ADMIN, ADMIN]) {
        expect(ids(isAdmin)).toContain(resolveSettingsTab(tab.id, isAdmin));
      }
    }
  });
});
