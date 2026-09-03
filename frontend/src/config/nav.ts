import {
  Activity,
  Bell,
  BookOpen,
  Bookmark,
  CloudOff,
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
  /** Hidden from non-admins. Settings is instance-wide configuration. */
  adminOnly?: boolean;
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
  // Chapters saved to Cache Storage in THIS browser, readable with no network.
  // TODO(1b): rename "Offline" -> "Downloads" and move to /downloads (spec §3.2).
  { href: "/offline", label: "Offline", icon: CloudOff },
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
  { href: "/settings", label: "Settings", icon: Settings, adminOnly: true },
  // Instance health. Admin-only for the same reason Settings is: it reports on
  // the server, not on the reader.
  { href: "/admin/status", label: "Status", icon: Activity, adminOnly: true },
];

/**
 * Mobile bottom-tab bar — the same five destinations, in the same order, as the
 * Flutter client's `NavigationBar`. Someone who uses both should not have to
 * learn two apps.
 *
 * "More" opens `/more`, not Settings. Five tabs cannot hold the whole app and a
 * phone has no sidebar, so without a real hub every route outside these five
 * would be reachable only by typing a URL.
 */
export const mobileNav: NavItem[] = [
  { href: "/library", label: "Library", icon: Library },
  { href: "/sources", label: "Sources", icon: Globe },
  { href: "/search", label: "Search", icon: Search },
  { href: "/more", label: "More", icon: Menu },
];
