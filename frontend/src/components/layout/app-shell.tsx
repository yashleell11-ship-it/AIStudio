"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { mobileNav } from "@/config/nav";
import { useShortcut } from "@/lib/keyboard";
import { ScrollContainerProvider } from "@/lib/scroll-container";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";
import { isPublicAuthPath } from "@/features/auth/access";
import { useCurrentUser } from "@/features/auth/hooks";
import { AuthPending } from "@/features/auth/components/auth-pending";
import { UpdateBanner } from "@/features/updates";
import {
  isPickerPath,
  moodShellBackground,
  PROFILE_PICKER_PATH,
  ProfileSwitcherChip,
  shouldRedirectToPicker,
  useActiveProfileStore,
} from "@/features/profiles";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

/**
 * Top-level frame selector. Auth screens (login/register) render full-bleed and
 * without a session; every other route renders the authenticated app frame,
 * gated by the route guard in `AuthenticatedShell`.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (isPublicAuthPath(pathname)) {
    return <>{children}</>;
  }

  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}

/**
 * The persistent application frame: sidebar + topbar + scrollable content.
 * Owns app-global shortcuts that act on the shell itself, and guards every
 * route it wraps — an unauthenticated visitor is redirected to /login and only
 * a resolved, signed-in session renders the frame.
 */
function AuthenticatedShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: user, isLoading } = useCurrentUser();
  const activeProfile = useActiveProfileStore((s) => s.activeProfile);
  const profilesHydrated = useActiveProfileStore((s) => s.hasHydrated);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const closeMobileSidebar = useUiStore((s) => s.closeMobileSidebar);
  const setSidebarCollapsed = useUiStore((s) => s.setSidebarCollapsed);
  const [scrollContainer, setScrollContainer] = useState<HTMLElement | null>(null);

  const isReaderChapter =
    /^\/reader\/\d+\/\d+/.test(pathname) ||
    /^\/reader\/online\//.test(pathname);

  const assignScrollContainer = useCallback((node: HTMLElement | null) => {
    setScrollContainer(node);
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1023px)");
    const apply = () => {
      if (media.matches) {
        setSidebarCollapsed(true);
      }
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [setSidebarCollapsed]);

  useEffect(() => {
    closeMobileSidebar();
  }, [pathname, closeMobileSidebar]);

  useShortcut({
    id: "shell.toggle-sidebar",
    keys: "mod+b",
    description: "Toggle the sidebar",
    group: "General",
    handler: useCallback(() => toggleSidebar(), [toggleSidebar]),
  });

  // Route guard: once the /auth/me probe settles, send unauthenticated visitors
  // to /login. `useCurrentUser` reports 401 as `null` (not an error), so a
  // missing session is `!user` here.
  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  // Profile gate: a signed-in visitor who hasn't chosen a reading profile is
  // routed to the picker. This runs AFTER auth (never instead of the remembered
  // login) and waits for the persisted selection to hydrate, so a reload never
  // bounces to the picker before the last choice is restored.
  useEffect(() => {
    if (isLoading || !user) return;
    if (
      shouldRedirectToPicker({
        authenticated: true,
        hydrated: profilesHydrated,
        hasActiveProfile: Boolean(activeProfile),
        pathname,
      })
    ) {
      router.replace(PROFILE_PICKER_PATH);
    }
  }, [isLoading, user, profilesHydrated, activeProfile, pathname, router]);

  // Resolving the session, or redirecting an unauthenticated visitor.
  if (isLoading || !user) {
    return <AuthPending />;
  }

  // The picker renders full-bleed (no sidebar/topbar) and owns its own
  // background — it is the profile hand-off screen, not an in-app page.
  if (isPickerPath(pathname)) {
    return <div className="h-dvh w-full overflow-hidden">{children}</div>;
  }

  // Tint the whole shell with the active profile's mood (muted, dark). The
  // reader keeps its obsidian background via the `bg-obsidian` override below.
  const shellBackground = moodShellBackground(activeProfile?.mood ?? "default");

  return (
    <div
      className="flex h-dvh w-full overflow-hidden bg-bg transition-[background] duration-500"
      style={{ background: shellBackground }}
    >
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-fg"
      >
        Skip to content
      </a>

      <Sidebar />

      <div className="relative flex min-w-0 flex-1 flex-col">
        <Topbar hideOnReader={isReaderChapter} />
        {/* Quick profile hand-off, anchored in the topbar band. Hidden on the
            reader (its topbar is hidden) and on narrow screens where the bar is
            crowded — switching is also available under Settings → Profiles. */}
        {!isReaderChapter ? (
          <ProfileSwitcherChip className="absolute left-1/2 top-2.5 z-40 hidden -translate-x-1/2 lg:flex" />
        ) : null}
        <ScrollContainerProvider container={scrollContainer}>
          <main
            id="main-content"
            ref={assignScrollContainer}
            tabIndex={-1}
            className={cn(
              "flex-1 overflow-y-auto outline-none",
              isReaderChapter && "bg-obsidian",
              !isReaderChapter && "max-md:pb-16",
            )}
          >
            {children}
          </main>
        </ScrollContainerProvider>

        {/* Mobile hybrid nav: glass bottom tab bar. Hidden on desktop (sidebar
            takes over) and inside the immersive reader. */}
        {!isReaderChapter ? <MobileBottomNav /> : null}
      </div>

      {/* Fixed to the layout root, outside the reader scroll container. */}
      <UpdateBanner />
    </div>
  );
}

function isTabActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Bottom tab bar for narrow viewports (`md:hidden`). Mirrors the desktop
 * sidebar's amber active state and is driven by `mobileNav` from the nav config.
 */
function MobileBottomNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="glass-panel absolute inset-x-0 bottom-0 z-30 flex h-16 items-stretch border-t border-border md:hidden"
    >
      {mobileNav.map((item) => {
        const active = isTabActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex flex-1 flex-col items-center justify-center gap-1 text-[0.65rem] font-medium uppercase tracking-widest transition-colors",
              active ? "text-primary" : "text-muted hover:text-fg",
            )}
          >
            <Icon className="size-5 shrink-0" aria-hidden />
            <span className="truncate">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
