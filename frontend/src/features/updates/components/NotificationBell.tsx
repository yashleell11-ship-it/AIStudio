"use client";

import Link from "next/link";
import { Bell } from "lucide-react";
import { useUnreadNotificationCount } from "@/features/updates/hooks";

export function NotificationBell() {
  const { data } = useUnreadNotificationCount();
  const count = data?.count ?? 0;

  return (
    <Link
      href="/updates"
      aria-label={`Updates${count > 0 ? `, ${count} unread` : ""}`}
      title="Updates"
      className="relative inline-flex size-11 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
    >
      <Bell className="size-5" aria-hidden />
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {count > 0 ? `${count} unread notifications` : "No unread notifications"}
      </span>
      {count > 0 ? (
        <span className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-primary text-[10px] font-medium text-primary-fg">
          {count > 9 ? "9+" : count}
        </span>
      ) : null}
    </Link>
  );
}
