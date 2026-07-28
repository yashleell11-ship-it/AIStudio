import {
  Activity,
  Bell,
  BookOpen,
  Bookmark,
  CloudOff,
  Download,
  Globe,
  History,
  Home,
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

/** Primary pillars of the app, in sidebar order. */
export const primaryNav: NavItem[] = [
  { href: "/", label: "Home", icon: Home },
  { href: "/library", label: "Library", icon: Library },
  { href: "/sources", label: "Sources", icon: Globe },
  { href: "/updates", label: "Updates", icon: Bell },
  { href: "/downloads", label: "Downloads", icon: Download },
  { href: "/reader", label: "Reader", icon: BookOpen },
  { href: "/search", label: "Search", icon: Search },
];

/** Secondary reading tools, grouped under a "More" header to reduce noise. */
export const moreNav: NavItem[] = [
  // Chapters stored in THIS browser, as opposed to /downloads, which is what
  // the server has fetched. The two are different places and different bytes.
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
 * Mobile bottom-tab bar — max 5 destinations. "More" is the catch-all that
 * opens Settings (the mobile hub for every secondary route).
 */
export const mobileNav: NavItem[] = [
  { href: "/", label: "Home", icon: Home },
  { href: "/library", label: "Library", icon: Library },
  { href: "/sources", label: "Sources", icon: Globe },
  { href: "/updates", label: "Updates", icon: Bell },
  { href: "/settings", label: "More", icon: Menu },
];
