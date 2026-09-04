"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import {
  isRoleVisibleNavItem,
  navSections,
  secondaryNav,
  type NavItem,
} from "@/config/nav";
import { useCurrentUser } from "@/features/auth/hooks";
import {
  ContentModeSwitch,
  isModeVisibleNavItem,
  useContentMode,
} from "@/features/content-mode";
import type { ContentMode } from "@/features/content-mode";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";

/**
 * Admin-only entries are hidden from non-admins, and mode-specific ones (OCR
 * search) from the mode they cannot serve. With novels disabled the mode test
 * passes everything, so this is the same list it has always been.
 */
function visibleNav(
  items: NavItem[],
  isAdmin: boolean,
  mode: ContentMode,
  novelsEnabled: boolean,
): NavItem[] {
  return items.filter(
    (item) =>
      isRoleVisibleNavItem(item, isAdmin) &&
      isModeVisibleNavItem(item.href, mode, novelsEnabled),
  );
}

function isNavActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({
  item,
  collapsed,
}: {
  item: NavItem;
  collapsed: boolean;
}) {
  const pathname = usePathname();
  const active = isNavActive(pathname, item.href);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
      className={cn(
        "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium uppercase tracking-widest transition-all",
        collapsed && "justify-center px-0 tracking-normal",
        active
          ? "bg-primary/10 text-primary shadow-glow"
          : "text-muted hover:bg-surface-2 hover:text-fg",
      )}
    >
      {active ? (
        <span
          className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary"
          aria-hidden
        />
      ) : null}
      <Icon
        className={cn(
          "size-5 shrink-0",
          active ? "text-primary" : "text-muted group-hover:text-fg",
        )}
        aria-hidden
      />
      {collapsed ? (
        <span className="sr-only">{item.label}</span>
      ) : (
        <span className="truncate">{item.label}</span>
      )}
    </Link>
  );
}

export function Sidebar({ className }: { className?: string }) {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const { data: user } = useCurrentUser();
  const { mode, novelsEnabled } = useContentMode();

  const isAdmin = user?.is_admin ?? false;
  const footerItems = visibleNav(secondaryNav, isAdmin, mode, novelsEnabled);

  return (
    <aside
      aria-label="Main navigation"
      className={cn(
        "hidden h-full shrink-0 flex-col border-r border-border bg-sidebar transition-[width] duration-200 md:flex",
        collapsed ? "w-[68px]" : "w-60",
        className,
      )}
    >
      <div
        className={cn(
          "flex h-14 items-center border-b border-border px-4",
          collapsed && "justify-center px-0",
        )}
      >
        {collapsed ? (
          <div
            className="flex size-9 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-fg"
            aria-hidden
          >
            MM
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <div
              className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-fg"
              aria-hidden
            >
              MM
            </div>
            <span className="font-display text-lg tracking-wide text-fg">ManhwaManiacs</span>
          </div>
        )}
      </div>

      <nav
        className="flex flex-1 flex-col gap-4 overflow-y-auto p-2"
        aria-label="Primary"
      >
        {/* Above every nav group on purpose: this is not a filter on one
            screen, it is what all of them are lists OF. Renders nothing at
            all when the server has novels off. */}
        <ContentModeSwitch collapsed={collapsed} />

        {navSections.map((section) => {
          const items = visibleNav(section.items, isAdmin, mode, novelsEnabled);
          if (items.length === 0) return null;
          return (
            <div key={section.label} className="flex flex-col gap-0.5">
              {/* Full-strength muted, not `text-muted/70`: the modifier
                  compiles to a colour-mix with transparent, which lands at
                  4.4:1 on the near-black page and fails WCAG AA. See the
                  opacity-modifier case in
                  features/preferences/theme-contrast.test.ts. */}
              {!collapsed ? (
                <p className="px-3 pb-1 pt-2 font-display text-xs uppercase tracking-widest text-muted">
                  {section.label}
                </p>
              ) : null}
              {items.map((item) => (
                <NavLink key={item.href} item={item} collapsed={collapsed} />
              ))}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-border p-2" aria-label="Secondary navigation">
        {footerItems.map((item) => (
          <NavLink key={item.href} item={item} collapsed={collapsed} />
        ))}
        {collapsed ? (
          <button
            type="button"
            onClick={toggleSidebar}
            className="mt-1 flex w-full items-center justify-center rounded-lg p-2 text-muted transition-colors hover:bg-surface-2 hover:text-fg"
            aria-label="Expand sidebar"
          >
            <ChevronRight className="size-4" />
          </button>
        ) : null}
      </div>
    </aside>
  );
}
