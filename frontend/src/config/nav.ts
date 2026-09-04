import {
  Activity,
  Bell,
  BookOpen,
  Bookmark,
  Download,
  Globe,
  History,
  Library,
  Menu,
  ScanText,
  Search,
  Settings,
  BarChart3,
  Heart,
  List,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /**
   * Hidden from non-admins. Only ever set on routes that administer the SERVER
   * or other accounts — never on per-reader preferences, which every signed-in
   * account owns a copy of.
   */
  adminOnly?: boolean;
}

/**
 * Whether an account may see a nav entry.
 *
 * The sidebar and the `/more` hub both ask here rather than each re-testing
 * `adminOnly` inline. Each carried its own copy of the flag and its own copy of
 * the test, and both marked `/settings` admin-only: with registration open that
 * left every account but the owner's with no route to a theme, a design preset,
 * reader defaults or the 18+ toggle. One predicate over one flag per route is
 * what keeps the two surfaces from drifting apart again.
 *
 * This hides a link; it does not authorize anything. The server admin-gates its
 * own instance-global writes (`PUT /updates/settings`, and the `updates_*`,
 * `source_cache_ttl_minutes` and profile-less `mature_content_enabled` fields of
 * `PUT /settings`), which is what actually stops a non-admin.
 */
export function isRoleVisibleNavItem(
  item: { adminOnly?: boolean },
  isAdmin: boolean,
): boolean {
  return !item.adminOnly || isAdmin;
}

/** A labelled group of nav items, rendered as a section in the sidebar. */
export interface NavSection {
  /** Syne section header shown above the group (hidden when collapsed). */
  label: string;
  items: NavItem[];
}

/**
 * Primary pillars of the app, in sidebar order.
 *
 * No "Home" entry: `/` is a bare redirect to `/library`, exactly as on mobile.
 * "Library" is the followed shelf; "Browse all" is the full catalogue that
 * used to live at `/library`.
 */
export const primaryNav: NavItem[] = [
  { href: "/library", label: "Library", icon: Library },
  { href: "/library/browse", label: "Browse all", icon: BookOpen },
  { href: "/sources", label: "Sources", icon: Globe },
  { href: "/updates", label: "Updates", icon: Bell },
  { href: "/search", label: "Search", icon: Search },
];

/** Secondary reading tools, grouped under a "More" header to reduce noise. */
export const moreNav: NavItem[] = [
  // Chapters saved to Cache Storage in THIS browser, readable with no network —
  // now the only kind of download there is (the server queue is gone).
  { href: "/downloads", label: "Downloads", icon: Download },
  { href: "/library/collections", label: "Collections", icon: List },
  { href: "/library/recommendations", label: "Recommendations", icon: Heart },
  { href: "/library/statistics", label: "Statistics", icon: BarChart3 },
  { href: "/library/history", label: "History", icon: History },
  { href: "/library/bookmarks", label: "Bookmarks", icon: Bookmark },
  { href: "/ocr", label: "OCR Search", icon: ScanText },
];

/** Sidebar body sections, in render order. Every route stays reachable here. */
export const navSections: NavSection[] = [
  { label: "Browse", items: primaryNav },
  { label: "More", items: moreNav },
];

/** Pinned to the bottom of the sidebar (account / instance config). */
export const secondaryNav: NavItem[] = [
  { href: "/profiles/manage", label: "Profiles", icon: Users },
  // Not admin-only: everything behind it is the reader's own — design preset,
  // theme, reader defaults, 18+ gate, shortcuts. The one instance-global panel
  // it hosts is gated inside the page (see `config/settings-tabs.ts`).
  { href: "/settings", label: "Settings", icon: Settings },
  // Instance health: it reports on the server, not on the reader.
  { href: "/admin/status", label: "Status", icon: Activity, adminOnly: true },
];

/**
 * Mobile bottom-tab bar — Library · Sources · Downloads · Search · More
 * (spec §3.8). "Downloads" here means chapters saved to this device; the server
 * download queue that used to own the name is gone.
 *
 * "More" opens `/more`, not Settings. Five tabs cannot hold the whole app and a
 * phone has no sidebar, so without a real hub every route outside these five
 * would be reachable only by typing a URL.
 */
export const mobileNav: NavItem[] = [
  { href: "/library", label: "Library", icon: Library },
  { href: "/sources", label: "Sources", icon: Globe },
  { href: "/downloads", label: "Downloads", icon: Download },
  { href: "/search", label: "Search", icon: Search },
  { href: "/more", label: "More", icon: Menu },
];
