"use client";

import { useState } from "react";
import {
  Bell,
  Download,
  Keyboard,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { DownloadSettingsPanel } from "@/features/downloads";
import { UpdateSettingsPanel } from "@/features/updates";
import { useUpdateSettings } from "@/features/updates/hooks";
import { MatureContentPanel } from "@/features/preferences";
import { KeyboardShortcutsPanel } from "@/components/settings/keyboard-shortcuts-panel";
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
    <div className="page-shell">
      <div className="page-container mx-auto max-w-6xl">
        <div className="mb-8">
          <h1 className="font-display text-4xl tracking-wide text-fg">Settings</h1>
          <p className="mt-1 text-sm text-muted">
            Configure automatic updates, downloads, and keyboard shortcuts.
          </p>
        </div>

        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <nav
            aria-label="Settings sections"
            className="glass-panel shrink-0 rounded-2xl p-2 lg:w-56"
          >
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
                        "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-all duration-200",
                        active
                          ? "bg-violet-500/15 text-violet-400 shadow-glow"
                          : "text-muted hover:bg-white/5 hover:text-fg",
                      )}
                    >
                      <Icon className="size-4 shrink-0" aria-hidden />
                      <span className="min-w-0">
                        <span className="block font-medium">{item.label}</span>
                        <span className="hidden text-xs text-muted lg:block">{item.description}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>

          <div className="min-w-0 flex-1 space-y-6">
            {activeTab === "general" && <UpdatesSettingsSection />}
            {activeTab === "downloads" && <DownloadSettingsPanel />}
            {activeTab === "content" && <MatureContentPanel />}
            {activeTab === "shortcuts" && <KeyboardShortcutsPanel />}
          </div>
        </div>

        <div className="mt-8 flex items-center gap-2 text-xs text-muted">
          <Bell className="size-3.5" aria-hidden />
          <span>Settings save immediately and apply without restarting the app.</span>
        </div>
      </div>
    </div>
  );
}
