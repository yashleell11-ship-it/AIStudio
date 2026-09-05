"use client";

import { useState } from "react";
import Link from "next/link";
import { Activity, Bell, ChevronRight, History } from "lucide-react";
import { NotificationSettingsPanel } from "@/features/updates";
import { BackupPanel } from "@/features/backup";
import { AccountSecurityPanel } from "@/features/auth/components/account-security-panel";
import { useCurrentUser } from "@/features/auth/hooks";
import {
  AppearancePanel,
  DesignPanel,
  MatureContentPanel,
  ReaderPanel,
} from "@/features/preferences";
import { KeyboardShortcutsPanel } from "@/components/settings/keyboard-shortcuts-panel";
import {
  resolveSettingsTab,
  visibleSettingsTabs,
  type SettingsTabId,
} from "@/config/settings-tabs";
import { FadeIn } from "@/components/premium/FadeIn";
import { GlassPanel } from "@/components/premium/GlassPanel";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { cn } from "@/lib/cn";

/** Reusable shortcut card in the header band. */
function ShortcutCard({
  href,
  icon: Icon,
  title,
  description,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <Link href={href} className="group block focus-visible:outline-none">
      <GlassPanel className="flex h-full items-center gap-4 rounded-3xl p-5 transition-colors group-hover:border-primary/40 group-focus-visible:border-primary/60 md:p-6">
        <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary">
          <Icon className="size-5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-lg tracking-wide text-fg">{title}</h2>
          <p className="mt-0.5 text-sm text-muted">{description}</p>
        </div>
        <ChevronRight
          className="size-5 shrink-0 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
          aria-hidden
        />
      </GlassPanel>
    </Link>
  );
}

export default function SettingsPage() {
  // Design first: it is the coarser of the two appearance axes — a preset
  // decides what the app is shaped like, a theme only what colour it is.
  const [requestedTab, setRequestedTab] = useState<SettingsTabId>("design");
  // System status and the update-checker panel are instance-wide, so they are
  // only offered to the account the API marks as admin — the same flag the
  // sidebar uses. Everything else on this page is the reader's own.
  const { data: user } = useCurrentUser();
  const isAdmin = user?.is_admin ?? false;
  const tabs = visibleSettingsTabs(isAdmin);
  const activeTab = resolveSettingsTab(requestedTab, isAdmin);

  return (
    <div className="page-shell bg-bg">
      <div className="page-container mx-auto max-w-6xl">
        <FadeIn className="mb-8" y={20}>
          <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted">
            Preferences
          </p>
          <HeroHeading className="leading-none md:text-6xl">
            Settings
          </HeroHeading>
          <p className="mt-3 max-w-xl text-sm text-muted">
            Reshape the app with a design preset, recolour it with a reading
            theme, tune the reader, set your mature-content gate and keyboard
            shortcuts, and manage your password and signed-in devices.
          </p>
        </FadeIn>

        <FadeIn className="mb-6" y={20} delay={0.05}>
          <div className="grid gap-4 lg:grid-cols-2">
            <ShortcutCard
              href="/library/history"
              icon={History}
              title="Reading History"
              description="Revisit everything you've read, most recent first."
            />
            {isAdmin ? (
              <ShortcutCard
                href="/admin/status"
                icon={Activity}
                title="System Status"
                description="Backend health, the update checker, source failures, and the queue."
              />
            ) : null}
          </div>
        </FadeIn>

        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <FadeIn y={20} delay={0.1} className="shrink-0 lg:w-56">
            <nav aria-label="Settings sections">
              <GlassPanel className="rounded-3xl p-2">
                <ul className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
                {tabs.map((item) => {
                  const Icon = item.icon;
                  const active = activeTab === item.id;
                  return (
                    <li key={item.id} className="shrink-0 lg:shrink">
                      <button
                        type="button"
                        onClick={() => setRequestedTab(item.id)}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-sm transition-all duration-200",
                          active
                            ? "bg-primary/15 text-primary shadow-glow"
                            : "text-muted hover:bg-surface-2 hover:text-fg",
                        )}
                      >
                        <Icon className="size-4 shrink-0" aria-hidden />
                        <span className="min-w-0">
                          <span className="block font-medium">{item.label}</span>
                          <span className="hidden text-xs text-muted lg:block">
                            {item.description}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
                </ul>
              </GlassPanel>
            </nav>
          </FadeIn>

          <FadeIn y={20} delay={0.15} className="min-w-0 flex-1">
            <div className="space-y-6">
              {activeTab === "design" && <DesignPanel />}
              {activeTab === "appearance" && <AppearancePanel />}
              {activeTab === "reader" && <ReaderPanel />}
              {/* Admin-gated in `visibleSettingsTabs`, and re-checked here so the
                  instance-global form cannot render off a stale tab. */}
              {activeTab === "notifications" && isAdmin && (
                <NotificationSettingsPanel />
              )}
              {activeTab === "content" && <MatureContentPanel />}
              {activeTab === "security" && <AccountSecurityPanel />}
              {activeTab === "shortcuts" && <KeyboardShortcutsPanel />}
              {/* Admin-gated in `visibleSettingsTabs`, and re-checked here for
                  the same reason as notifications: the panel restores the whole
                  instance database, not this reader's data. */}
              {activeTab === "backup" && isAdmin && <BackupPanel />}
            </div>
          </FadeIn>
        </div>

        <div className="mt-8 flex items-center gap-2 text-xs text-muted">
          <Bell className="size-3.5" aria-hidden />
          <span>Settings save immediately and apply without restarting the app.</span>
        </div>
      </div>
    </div>
  );
}
