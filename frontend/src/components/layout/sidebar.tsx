"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { primaryNav, secondaryNav, type NavItem } from "@/config/nav";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";

function isNavActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  collapsed: boolean;
  onNavigate: () => void;
}) {
  const pathname = usePathname();
  const active = isNavActive(pathname, item.href);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
      className={cn(
        "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-all",
        collapsed && "justify-center px-0",
        active
          ? "bg-violet-500/10 text-violet-400"
          : "text-muted hover:bg-white/5 hover:text-fg",
      )}
    >
      {active ? (
        <span
          className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-violet-500"
          aria-hidden
        />
      ) : null}
      <Icon
        className={cn(
          "size-5 shrink-0",
          active ? "text-violet-400" : "text-muted group-hover:text-fg",
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

export function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const mobileSidebarOpen = useUiStore((s) => s.mobileSidebarOpen);
  const closeMobileSidebar = useUiStore((s) => s.closeMobileSidebar);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);

  const isMobileDrawer = mobileSidebarOpen;
  const showCollapsed = collapsed && !isMobileDrawer;

  return (
    <aside
      aria-label="Main navigation"
      className={cn(
        "flex h-full flex-col border-r border-border/50 bg-sidebar transition-[width,transform] duration-200",
        "fixed inset-y-0 left-0 z-40 lg:relative lg:z-auto lg:translate-x-0",
        showCollapsed ? "w-[68px]" : "w-60",
        !isMobileDrawer && collapsed ? "-translate-x-full lg:translate-x-0" : "translate-x-0",
      )}
    >
      <div
        className={cn(
          "flex h-14 items-center border-b border-border/50 px-4",
          showCollapsed && "justify-center px-0",
        )}
      >
        {showCollapsed ? (
          <div
            className="flex size-9 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-cyan-500 text-xs font-bold text-white"
            aria-hidden
          >
            AS
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <div
              className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-cyan-500 text-xs font-bold text-white"
              aria-hidden
            >
              AS
            </div>
            <span className="font-display text-lg tracking-wide text-fg">AIStudio</span>
          </div>
        )}
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2" aria-label="Primary">
        {primaryNav.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            collapsed={showCollapsed}
            onNavigate={closeMobileSidebar}
          />
        ))}
      </nav>

      <div className="border-t border-border/50 p-2" aria-label="Secondary navigation">
        {secondaryNav.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            collapsed={showCollapsed}
            onNavigate={closeMobileSidebar}
          />
        ))}
        {showCollapsed ? (
          <button
            type="button"
            onClick={toggleSidebar}
            className="mt-1 flex w-full items-center justify-center rounded-lg p-2 text-muted transition-colors hover:bg-white/5 hover:text-fg"
            aria-label="Expand sidebar"
          >
            <ChevronRight className="size-4" />
          </button>
        ) : null}
      </div>
    </aside>
  );
}
