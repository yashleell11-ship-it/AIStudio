"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Activity,
  Bell,
  BookOpenText,
  ChevronRight,
  History,
  Keyboard,
  LayoutTemplate,
  Palette,
  ShieldAlert,
} from "lucide-react";
import { NotificationSettingsPanel } from "@/features/updates";
import { useCurrentUser } from "@/features/auth/hooks";
import {
  AppearancePanel,
  DesignPanel,
  MatureContentPanel,
  ReaderPanel,
} from "@/features/preferences";
import { KeyboardShortcutsPanel } from "@/components/settings/keyboard-shortcuts-panel";
import { FadeIn } from "@/components/premium/FadeIn";
import { GlassPanel } from "@/components/premium/GlassPanel";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { cn } from "@/lib/cn";

type SettingsTab =
  | "design"
  | "appearance"
  | "reader"
  | "notifications"
  | "content"
  | "shortcuts";

const NAV_ITEMS: {
  id: SettingsTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}[] = [
  {
    id: "design",
    label: "Design",
    icon: LayoutTemplate,
    description: "How the app is shaped",
  },
  {
    id: "appearance",
    label: "Appearance",
    icon: Palette,
    description: "Reading theme",
  },
  {
    id: "reader",
    label: "Reader",
    icon: BookOpenText,
    description: "Page gap and cinema mode",
  },
  {
    id: "notifications",
    label: "Notifications",
    icon: Bell,
    description: "Update checks and alerts",
  },
  {
    id: "content",
    label: "Content",
    icon: ShieldAlert,
    description: "Mature (18+) content",
  },
  {
    id: "shortcuts",
    label: "Shortcuts",
    icon: Keyboard,
    description: "Keyboard bindings",
  },
];

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
  const [activeTab, setActiveTab] = useState<SettingsTab>("design");
  // System status is instance-wide health, so the entry point is only offered
  // to the account the API marks as admin — the same flag the sidebar uses.
  const { data: user } = useCurrentUser();

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
            theme, tune the reader, and configure automatic updates, mature
            content, and keyboard shortcuts.
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
            {user?.is_admin ? (
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
                {NAV_ITEMS.map((item) => {
                  const Icon = item.icon;
                  const active = activeTab === item.id;
                  return (
                    <li key={item.id} className="shrink-0 lg:shrink">
                      <button
                        type="button"
                        onClick={() => setActiveTab(item.id)}
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
              {activeTab === "notifications" && <NotificationSettingsPanel />}
              {activeTab === "content" && <MatureContentPanel />}
              {activeTab === "shortcuts" && <KeyboardShortcutsPanel />}
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
