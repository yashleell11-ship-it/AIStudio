"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { CommandPalette } from "@/components/command-palette";
import { ShortcutsDialog } from "@/components/keyboard";
import { mobileNav } from "@/config/nav";
import { HELP_SHORTCUT_KEYS, useShortcut } from "@/lib/keyboard";
import { ScrollContainerProvider } from "@/lib/scroll-container";
import {
  isImmersiveNovelPath,
  isImmersivePath,
  isImmersiveReaderPath,
} from "@/lib/reader-route";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";
// Direct, not via the `@/features/preferences` barrel: that barrel also exports
// the settings panels, and the shell wraps every page.
import { useApplyReadingTheme } from "@/features/preferences/theme-store";
import { isPublicAuthPath } from "@/features/auth/access";
import { useCurrentUser } from "@/features/auth/hooks";
import { AuthPending } from "@/features/auth/components/auth-pending";
import { isSessionUnresolved, resolveSessionGate } from "@/features/offline/session-gate";
import { FirstRunHint } from "@/features/library";
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

  // Above the auth branch on purpose: the reading theme paints the login and
  // register screens too. Without a profile there is no scoped value to read,
  // so those screens land on the OS preference — which is the right answer for
  // a screen that belongs to nobody yet.
  useApplyReadingTheme();

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
  const { data: user, isLoading, error: sessionError } = useCurrentUser();
  const activeProfile = useActiveProfileStore((s) => s.activeProfile);
  const profilesHydrated = useActiveProfileStore((s) => s.hasHydrated);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const closeMobileSidebar = useUiStore((s) => s.closeMobileSidebar);
  const setSidebarCollapsed = useUiStore((s) => s.setSidebarCollapsed);
  const shortcutsOpen = useUiStore((s) => s.shortcutsOpen);
  const toggleShortcuts = useUiStore((s) => s.toggleShortcuts);
  const closeShortcuts = useUiStore((s) => s.closeShortcuts);
  const [scrollContainer, setScrollContainer] = useState<HTMLElement | null>(null);

  // Both readers lose the app chrome; only the manga one gets the obsidian
  // page, because the novel reader paints its own reading palette and a
  // near-black shell under a Paper page would defeat the point of choosing it.
  const isMangaChapter = isImmersiveReaderPath(pathname);
  const isNovelChapter = isImmersiveNovelPath(pathname);
  const isReaderChapter = isImmersivePath(pathname);

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

  // App-wide, so "what can I press here?" has the same answer on every screen.
  // The reader used to own this binding and list only its own group; the sheet
  // now reads the whole live registry (see `ShortcutsDialog`).
  useShortcut({
    id: "shell.shortcuts",
    keys: HELP_SHORTCUT_KEYS,
    description: "Show keyboard shortcuts",
    group: "General",
    handler: useCallback(() => toggleShortcuts(), [toggleShortcuts]),
  });

  // Route guard: once the /auth/me probe settles, send unauthenticated visitors
  // to /login. `useCurrentUser` reports 401 as `null` (not an error), so a
  // missing session is `!user` here.
  //
  // A probe that never REACHED the server is a different thing and must not
  // redirect: offline, /login is just as unreachable as the page being left,
  // so the reader would be bounced away from chapters already saved on the
  // device. See `features/offline/session-gate.ts`.
  const sessionGate = resolveSessionGate({
    isLoading,
    hasUser: Boolean(user),
    error: sessionError,
  });

  useEffect(() => {
    if (sessionGate === "redirect") {
      router.replace("/login");
    }
  }, [sessionGate, router]);

  // Profile gate: a signed-in visitor who hasn't chosen a reading profile is
  // routed to the picker. This runs AFTER auth (never instead of the remembered
  // login) and waits for the persisted selection to hydrate, so a reload never
  // bounces to the picker before the last choice is restored.
  useEffect(() => {
    if (isSessionUnresolved(sessionGate)) return;
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
  }, [sessionGate, profilesHydrated, activeProfile, pathname, router]);

  // Resolving the session, or redirecting an unauthenticated visitor. An
  // unanswered probe is neither: the app renders on what this device already
  // has, and the guard above takes over the moment the server can be reached.
  if (isSessionUnresolved(sessionGate)) {
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
      {/* First tab stop on every page. `focus:` rather than `focus-visible:`
          so it also appears for a pointer-driven focus, and z-60 so it is not
          covered by the topbar or the update banner. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:font-medium focus:text-primary-fg focus:shadow-glow"
      >
        Skip to content
      </a>

      <Sidebar />

      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* The novel reader paints its own page, and that page can be cream.
            The app's dark bar sitting across the top of it reads as a second
            header and as a hole punched in the book — the same reason the
            reader's type panel borrows the reading palette instead of the
            app's chrome. The running head carries the back arrow, the progress
            and the settings, so nothing is lost with it gone.

            The manga reader keeps the bar exactly as it has always had it: its
            page is obsidian, so the chrome above it agrees with it. */}
        {isNovelChapter ? null : <Topbar hideOnReader={isMangaChapter} />}
        {/* Quick profile hand-off, anchored in the topbar band. Hidden on the
            reader (its topbar is hidden) and on narrow screens where the bar is
            crowded — switching is also available under Settings → Profiles. */}
        {!isReaderChapter ? (
          <ProfileSwitcherChip className="absolute left-1/2 top-2.5 z-40 hidden -translate-x-1/2 lg:flex" />
        ) : null}
        {/* Renders nothing once anything is followed, or on a route where it
            would be redundant (see `shouldShowFirstRunHint`). */}
        {!isReaderChapter ? <FirstRunHint /> : null}
        <ScrollContainerProvider container={scrollContainer}>
          <main
            id="main-content"
            ref={assignScrollContainer}
            tabIndex={-1}
            className={cn(
              "flex-1 overflow-y-auto outline-none",
              isMangaChapter && "bg-obsidian",
              // Clears the floating tab pill (56px tall + its 16px inset and
              // safe-area padding) so the last row of covers is never under it.
              !isReaderChapter && "max-md:pb-24",
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

      {/* Always mounted so its ⌘K binding is registered; renders nothing until
          opened. Inside the authenticated shell because half of what it offers
          (the library, the installed sources, sign out) needs a session. */}
      <CommandPalette />

      {/* Mounted at the shell root so it paints above page chrome — including
          the reader's fixed controls — on every route. */}
      <ShortcutsDialog open={shortcutsOpen} onClose={closeShortcuts} />
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
 * Bottom tab bar for narrow viewports (`md:hidden`).
 *
 * A floating, rounded, frosted pill rather than a full-bleed bar — the same
 * shape as the Flutter client's `NavigationBar`: inset by 16px, 20px radius,
 * near-black surface at ~0.85 alpha over a backdrop blur, a subtle warm-neutral
 * border, and a soft black + amber shadow. The active destination gets an amber
 * wash behind it and only the active label is shown, matching
 * `NavigationDestinationLabelBehavior.onlyShowSelected`.
 *
 * `pb-[env(safe-area-inset-bottom)]` keeps it clear of the iOS home indicator
 * when the site is installed and running edge to edge.
 */
function MobileBottomNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="pointer-events-none absolute inset-x-0 bottom-0 z-30 px-4 pb-[max(env(safe-area-inset-bottom),0.5rem)] md:hidden"
    >
      <div className="pointer-events-auto flex items-stretch gap-1 rounded-[20px] border border-border bg-surface/85 p-1.5 shadow-[0_6px_20px_rgba(0,0,0,0.43),0_4px_24px_rgba(245,158,11,0.09)] backdrop-blur-[18px]">
        {mobileNav.map((item) => {
          const active = isTabActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex flex-1 flex-col items-center justify-center gap-0.5 rounded-2xl py-2 transition-colors",
                active ? "bg-primary/12 text-primary" : "text-muted hover:text-fg",
              )}
            >
              <Icon className="size-[22px] shrink-0" aria-hidden />
              {/* Only the active label renders, so five destinations fit a phone
                  without truncating. The inactive labels stay in the tree for
                  assistive tech. */}
              <span
                className={cn(
                  "max-w-full truncate text-[0.6875rem] font-semibold leading-none",
                  !active && "sr-only",
                )}
              >
                {item.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
