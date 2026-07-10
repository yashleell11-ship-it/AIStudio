import {
  Bell,
  BookOpen,
  Bookmark,
  Download,
  Globe,
  History,
  Home,
  Library,
  Search,
  Settings,
  BarChart3,
  Heart,
  List,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Primary pillars of the app, in sidebar order. */
export const primaryNav: NavItem[] = [
  { href: "/", label: "Dashboard", icon: Home },
  { href: "/library", label: "Library", icon: Library },
  { href: "/library/collections", label: "Collections", icon: List },
  { href: "/library/recommendations", label: "Recommendations", icon: Heart },
  { href: "/library/statistics", label: "Statistics", icon: BarChart3 },
  { href: "/library/history", label: "History", icon: History },
  { href: "/library/bookmarks", label: "Bookmarks", icon: Bookmark },
  { href: "/sources", label: "Sources", icon: Globe },
  { href: "/downloads", label: "Downloads", icon: Download },
  { href: "/updates", label: "Updates", icon: Bell },
  { href: "/reader", label: "Reader", icon: BookOpen },
  { href: "/search", label: "Search", icon: Search },
];

/** Pinned to the bottom of the sidebar. */
export const secondaryNav: NavItem[] = [
  { href: "/settings", label: "Settings", icon: Settings },
];
