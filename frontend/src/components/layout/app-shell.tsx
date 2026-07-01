"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useShortcut } from "@/lib/keyboard";
import { ScrollContainerProvider } from "@/lib/scroll-container";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

/**
 * The persistent application frame: sidebar + topbar + scrollable content.
 * Owns app-global shortcuts that act on the shell itself.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
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
              isReaderChapter && "bg-bg",
            )}
          >
            {children}
          </main>
        </ScrollContainerProvider>
      </div>
    </div>
  );
}
