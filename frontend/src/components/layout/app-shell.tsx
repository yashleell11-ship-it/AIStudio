"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useShortcut } from "@/lib/keyboard";
import { ScrollContainerProvider } from "@/lib/scroll-container";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";
import { isPublicAuthPath } from "@/features/auth/access";
import { useCurrentUser } from "@/features/auth/hooks";
import { AuthPending } from "@/features/auth/components/auth-pending";
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
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const mobileSidebarOpen = useUiStore((s) => s.mobileSidebarOpen);
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

  // Resolving the session, or redirecting an unauthenticated visitor.
  if (isLoading || !user) {
    return <AuthPending />;
  }

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-bg">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-fg"
      >
        Skip to content
      </a>

      {mobileSidebarOpen ? (
        <button
          type="button"
          aria-label="Close sidebar"
          className="fixed inset-0 z-30 bg-bg/80 lg:hidden"
          onClick={closeMobileSidebar}
        />
      ) : null}

      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar hideOnReader={isReaderChapter} />
        <ScrollContainerProvider container={scrollContainer}>
          <main
            id="main-content"
            ref={assignScrollContainer}
            tabIndex={-1}
            className={cn(
              "flex-1 overflow-y-auto outline-none",
              isReaderChapter && "bg-obsidian",
            )}
          >
            {children}
          </main>
        </ScrollContainerProvider>
      </div>
    </div>
  );
}
