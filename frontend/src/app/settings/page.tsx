"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Bell,
  ChevronRight,
  Download,
  History,
  Keyboard,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { DownloadSettingsPanel } from "@/features/downloads";
import { UpdateSettingsPanel } from "@/features/updates";
import { useUpdateSettings } from "@/features/updates/hooks";
import { MatureContentPanel } from "@/features/preferences";
import { KeyboardShortcutsPanel } from "@/components/settings/keyboard-shortcuts-panel";
import { FadeIn } from "@/components/premium/FadeIn";
import { GlassPanel } from "@/components/premium/GlassPanel";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { cn } from "@/lib/cn";

type SettingsTab = "general" | "downloads" | "content" | "shortcuts";

const NAV_ITEMS: {
  id: SettingsTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}[] = [
  {
    id: "general",
    label: "General",
    icon: RefreshCw,
    description: "Updates and notifications",
  },
  {
    id: "downloads",
    label: "Downloads",
    icon: Download,
    description: "Queue and concurrency",
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

function UpdatesSettingsSection() {
  const settings = useUpdateSettings();
  return (
    <UpdateSettingsPanel
      settings={settings.data}
      isLoading={settings.isLoading}
      isError={settings.isError}
      error={settings.error}
      onRetry={() => settings.refetch()}
    />
  );
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("general");

  return (
    <div className="page-shell bg-bg">
      <div className="page-container mx-auto max-w-6xl">
        <FadeIn className="mb-8" y={20}>
          <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted">
            Preferences
          </p>
          <HeroHeading className="text-[2.75rem] leading-none md:text-6xl">
            Settings
          </HeroHeading>
          <p className="mt-3 max-w-xl text-sm text-muted">
            Configure automatic updates, downloads, and keyboard shortcuts.
          </p>
        </FadeIn>

        <FadeIn className="mb-6" y={20} delay={0.05}>
          <Link
            href="/library/history"
            className="group block focus-visible:outline-none"
          >
            <GlassPanel className="flex items-center gap-4 rounded-3xl p-5 transition-colors group-hover:border-primary/40 group-focus-visible:border-primary/60 md:p-6">
              <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary">
                <History className="size-5" aria-hidden />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="font-display text-lg tracking-wide text-fg">
                  Reading History
                </h2>
                <p className="mt-0.5 text-sm text-muted">
                  Revisit everything you&apos;ve read, most recent first.
                </p>
              </div>
              <ChevronRight
                className="size-5 shrink-0 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
                aria-hidden
              />
            </GlassPanel>
          </Link>
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
              {activeTab === "general" && <UpdatesSettingsSection />}
              {activeTab === "downloads" && <DownloadSettingsPanel />}
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
