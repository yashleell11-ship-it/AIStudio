"use client";

import { useSyncExternalStore } from "react";
import { Keyboard, PanelLeft, Wifi } from "lucide-react";
import { Button } from "@/components/ui/button";
import { NotificationBell } from "@/features/updates";
import { UserMenu } from "@/features/auth/components/user-menu";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";

interface TopbarProps {
  hideOnReader?: boolean;
}

function formatClock(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function subscribeToClock(onStoreChange: () => void) {
  const interval = window.setInterval(onStoreChange, 30_000);
  return () => window.clearInterval(interval);
}

function getClockSnapshot() {
  return formatClock(new Date());
}

function getClockServerSnapshot() {
  return "--:--";
}

export function Topbar({ hideOnReader = false }: TopbarProps) {
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const toggleShortcuts = useUiStore((s) => s.toggleShortcuts);
  const time = useSyncExternalStore(
    subscribeToClock,
    getClockSnapshot,
    getClockServerSnapshot,
  );

  return (
    <header
      className={cn(
        // `pt-[env(safe-area-inset-top)]` clears the iOS notch / Dynamic Island
        // when installed as a standalone PWA (`black-translucent` status bar —
        // see layout.tsx — draws page content straight under it). `min-h-*`
        // rather than `h-*` so that padding ADDS space above the usual 56px/44px
        // bar instead of eating into it and squeezing the toggle/notification/
        // clock row.
        // Below `md` this is a bare action strip, not a bar: no fill, no rule,
        // no product name. The Flutter client's tab screens use a transparent,
        // zero-elevation `AppBar` carrying only its actions, and every screen
        // here already states its own name in the heading directly underneath.
        // Painting a second, titled band above that heading is what made the
        // phone layout read as two stacked headers on every route.
        //
        // From `md` up the sidebar is on screen and the bar separates the app
        // frame from the page, so it keeps its fill and its rule there.
        "app-no-drag flex shrink-0 items-center gap-3 px-4 pt-[env(safe-area-inset-top)] md:border-b md:border-border md:bg-bg-void/80 md:backdrop-blur-sm",
        hideOnReader
          ? // …and on a phone held sideways it goes entirely. 375px of height
            // is all there is in that orientation, and the reader's own control
            // bar already carries the way back to the series. Same 500px line
            // the shell uses to drop the desktop rail here (`app-shell.tsx`),
            // for the same reason: height is what tells a landscape phone apart
            // from a desktop window this wide.
            "min-h-[calc(3.5rem+env(safe-area-inset-top))] max-lg:min-h-[calc(2.75rem+env(safe-area-inset-top))] [@media(max-height:500px)]:hidden"
          : "min-h-[calc(3.5rem+env(safe-area-inset-top))]",
      )}
    >
      <Button
        variant="ghost"
        size="icon"
        onClick={toggleSidebar}
        aria-label="Toggle sidebar"
        title="Toggle sidebar (Ctrl/Cmd + B)"
        className="hidden text-muted hover:text-primary lg:inline-flex"
      >
        <PanelLeft className="size-5" />
      </Button>

      <div className="flex flex-1 items-center justify-end gap-3">
        {/* The only advertisement the keyboard layer gets. Pointer-sized
            screens only: on a touch device the sheet lists keys nobody has. */}
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleShortcuts}
          aria-label="Keyboard shortcuts"
          title="Keyboard shortcuts (?)"
          className="hidden text-muted hover:text-primary lg:inline-flex"
        >
          <Keyboard className="size-5" />
        </Button>

        <NotificationBell />
        <div className="hidden items-center gap-2 text-xs text-muted sm:flex">
          <Wifi className="size-3.5" aria-hidden />
          <time className="font-mono tabular-nums">{time}</time>
        </div>
        {/* Separates the bell from the account menu only where the bar is a
            filled surface. On the phone strip there is nothing to separate. */}
        <div className="hidden h-6 w-px bg-border md:block" aria-hidden />
        <UserMenu />
      </div>
    </header>
  );
}
