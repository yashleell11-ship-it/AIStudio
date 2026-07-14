"use client";

import { useRouter } from "next/navigation";
import { ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/cn";
import { PROFILE_PICKER_PATH } from "../access";
import { useActiveProfileStore } from "../store";
import { ProfileAvatar } from "./profile-avatar";

/**
 * App-bar chip showing the active reading profile. Clicking it returns to the
 * picker for a quick hand-off to another profile — no logout, the session and
 * remembered login stay intact. Renders nothing until a profile is active.
 */
export function ProfileSwitcherChip({ className }: { className?: string }) {
  const router = useRouter();
  const activeProfile = useActiveProfileStore((s) => s.activeProfile);

  if (!activeProfile) return null;

  return (
    <button
      type="button"
      onClick={() => router.push(PROFILE_PICKER_PATH)}
      aria-label={`Switch profile — currently ${activeProfile.name}`}
      title="Switch profile"
      className={cn(
        "flex items-center gap-2 rounded-full border border-border/50 bg-void/70 py-1 pl-1 pr-2.5 text-sm text-fg/90 shadow-glass backdrop-blur-sm transition-colors",
        "hover:border-primary/40 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
        className,
      )}
    >
      <ProfileAvatar avatarKey={activeProfile.avatar_key} size="sm" />
      <span className="max-w-[9rem] truncate font-medium">{activeProfile.name}</span>
      <ChevronsUpDown className="size-4 shrink-0 text-muted" aria-hidden />
    </button>
  );
}
