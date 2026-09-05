"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { moreSections } from "@/config/more-nav";
import { isRoleVisibleNavItem } from "@/config/nav";
import { useCurrentUser } from "@/features/auth/hooks";
import { ContentModeSwitch } from "@/features/content-mode";
import { useUnreadNotificationCount } from "@/features/updates/hooks";

/**
 * The "More" tab: every destination the five-tab bar cannot hold.
 *
 * On desktop the sidebar covers these; a phone has no sidebar, so this screen
 * is the only way to reach roughly a third of the app without typing a URL.
 * Mirrors `more_screen.dart` — same groups, same order.
 *
 * That includes the Manga / Novels switch. It was mounted in exactly one place,
 * the sidebar, which is `hidden … md:flex` — so below 768px the whole novel
 * half of the app was unreachable, and the mode is per-browser localStorage, so
 * flipping it on a laptop did not carry over. `more_screen.dart` puts the same
 * chip at the top of this screen for the same reason.
 */
export default function MorePage() {
  const { data: user } = useCurrentUser();
  const isAdmin = user?.is_admin ?? false;
  const unread = useUnreadNotificationCount();
  const unreadCount = unread.data?.count ?? 0;

  return (
    <div className="px-5 pb-8 pt-6 md:px-8">
      <h1 className="font-display text-3xl font-bold text-fg">More</h1>

      {/* Renders nothing at all when the server has novels off, exactly as in
          the sidebar — a dark deployment keeps the screen it has today. */}
      <ContentModeSwitch className="mt-5" />

      <div className="mt-6 space-y-8">
        {moreSections.map((section) => {
          const items = section.items.filter((item) =>
            isRoleVisibleNavItem(item, isAdmin),
          );
          if (items.length === 0) return null;

          return (
            <section key={section.label}>
              <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">
                {section.label}
              </h2>
              <div className="space-y-2">
                {items.map((item) => {
                  const Icon = item.icon;
                  const badge = item.href === "/updates" && unreadCount > 0 ? unreadCount : null;

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className="flex items-center gap-3 rounded-2xl border border-border bg-surface px-3 py-3 transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary">
                        <Icon className="size-5" aria-hidden />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium text-fg">
                            {item.label}
                          </span>
                          {badge ? (
                            <span className="shrink-0 rounded-full bg-primary px-1.5 py-px text-[0.625rem] font-bold text-primary-fg">
                              {badge}
                            </span>
                          ) : null}
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-muted">
                          {item.description}
                        </span>
                      </span>
                      <ChevronRight className="size-4 shrink-0 text-muted" aria-hidden />
                    </Link>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
