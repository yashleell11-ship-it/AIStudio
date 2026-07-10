"use client";

import { useSyncExternalStore } from "react";
import { PanelLeft, Wifi } from "lucide-react";
import { Button } from "@/components/ui/button";
import { NotificationBell } from "@/features/updates";
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
  const time = useSyncExternalStore(
    subscribeToClock,
    getClockSnapshot,
    getClockServerSnapshot,
  );

  return (
    <header
      className={cn(
        "app-no-drag flex h-14 shrink-0 items-center gap-3 border-b border-border/50 bg-void/80 px-4 backdrop-blur-sm",
        hideOnReader && "lg:flex max-lg:h-11",
      )}
    >
      <Button
        variant="ghost"
        size="icon"
        onClick={toggleSidebar}
        aria-label="Toggle sidebar"
        title="Toggle sidebar (Ctrl/Cmd + B)"
        className="text-muted hover:text-fg"
      >
        <PanelLeft className="size-5" />
      </Button>

      <div className="flex items-center gap-2 lg:hidden">
        <div
          className="size-2 rounded-full bg-gradient-to-r from-violet-500 to-cyan-500"
          aria-hidden
        />
        <span className="font-display text-base tracking-wide text-fg">ManhwaManiacs</span>
      </div>

      <div className="flex flex-1 items-center justify-end gap-3">
        <NotificationBell />
        <div className="hidden items-center gap-2 text-xs text-muted sm:flex">
          <Wifi className="size-3.5" aria-hidden />
          <time className="font-mono tabular-nums">{time}</time>
        </div>
      </div>
    </header>
  );
}
