import {
  Bell,
  BookOpenText,
  DatabaseBackup,
  Keyboard,
  LayoutTemplate,
  Palette,
  ShieldAlert,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { isRoleVisibleNavItem } from "./nav";

export type SettingsTabId =
  | "design"
  | "appearance"
  | "reader"
  | "notifications"
  | "content"
  | "security"
  | "shortcuts"
  | "backup";

export interface SettingsTab {
  id: SettingsTabId;
  label: string;
  icon: LucideIcon;
  description: string;
  /** Instance-global, not per-reader. See `notifications` below. */
  adminOnly?: boolean;
}

/**
 * The sections of `/settings`, in render order.
 *
 * All but two are the reader's own, which is why the route itself is not
 * admin-only and why this list mirrors `settings_screen.dart` — the Flutter
 * client shows the same preferences to every account and gates none of them.
 *
 * "Notifications" is the first exception and the reason the split exists: it edits the
 * singleton `UpdateSettings` row — whether the checker runs at all, how often it
 * sweeps every followed series, whether it runs on startup — which is one
 * setting for the whole instance, not one per reader. The backend already
 * refuses it to non-admins (`PUT /updates/settings` carries
 * `require_admin_user`), so leaving the tab visible would only offer every
 * account a form whose Save returns 403. Mobile has no equivalent panel at all.
 *
 * "Backup" is the second, and is gated harder for the same reason the backend
 * gates it: the file is the whole SQLite database — every account on the
 * instance — and restoring one replaces it. Mobile keeps this on its own screen
 * at `/settings/backup`; on the web it is a section of this page.
 */
export const SETTINGS_TABS: SettingsTab[] = [
  {
    id: "design",
    label: "Design",
    icon: LayoutTemplate,
    description: "How the app is shaped",
  },
  {
    id: "appearance",
    label: "Appearance",
    icon: Palette,
    description: "Reading theme",
  },
  {
    id: "reader",
    label: "Reader",
    icon: BookOpenText,
    description: "Page gap and cinema mode",
  },
  {
    id: "notifications",
    label: "Notifications",
    icon: Bell,
    description: "Update checks and alerts",
    adminOnly: true,
  },
  {
    id: "content",
    label: "Content",
    icon: ShieldAlert,
    description: "Mature (18+) content",
  },
  {
    id: "security",
    label: "Security",
    icon: ShieldCheck,
    description: "Password and sessions",
  },
  {
    id: "shortcuts",
    label: "Shortcuts",
    icon: Keyboard,
    description: "Keyboard bindings",
  },
  {
    id: "backup",
    label: "Backup",
    icon: DatabaseBackup,
    description: "Export and restore",
    adminOnly: true,
  },
];

/** The tabs this account may open. Never empty: most of the page is per-reader. */
export function visibleSettingsTabs(isAdmin: boolean): SettingsTab[] {
  return SETTINGS_TABS.filter((tab) => isRoleVisibleNavItem(tab, isAdmin));
}

/**
 * The tab to render: the requested one when this account may open it, and
 * otherwise the first it may. Resolving here rather than trusting the click
 * handler means a panel cannot stay mounted through a change of account, and
 * that no admin panel renders during the window before `GET /auth/me` has
 * answered and `is_admin` still reads false.
 */
export function resolveSettingsTab(
  requested: SettingsTabId,
  isAdmin: boolean,
): SettingsTabId {
  const tabs = visibleSettingsTabs(isAdmin);
  return tabs.some((tab) => tab.id === requested) ? requested : tabs[0].id;
}
