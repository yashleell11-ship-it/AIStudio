"use client";

import { cn } from "@/lib/cn";
import type { Profile } from "../types";
import { ProfileAvatar } from "./profile-avatar";

/** How a tile is drawn while the picker resolves a selection. */
export type TilePhase = "idle" | "selected" | "dimmed";

interface ProfileTileProps {
  profile: Profile;
  /** Position in the row, used to stagger the entrance. */
  index: number;
  phase: TilePhase;
  reducedMotion: boolean;
  disabled: boolean;
  onSelect: (profile: Profile) => void;
}

const EASE_OUT_CUBIC = "cubic-bezier(0.215, 0.61, 0.355, 1)";

/**
 * One selectable profile in the picker. Entrance is a staggered fade+scale;
 * selecting one scales it up (1.08) while the rest dim and blur. Under reduced
 * motion every transform is dropped and states switch instantly.
 */
export function ProfileTile({
  profile,
  index,
  phase,
  reducedMotion,
  disabled,
  onSelect,
}: ProfileTileProps) {
  const entrance = reducedMotion
    ? undefined
    : {
        animation: `mm-profile-in 340ms ${EASE_OUT_CUBIC} both`,
        animationDelay: `${index * 80}ms`,
      };

  const transform = reducedMotion
    ? undefined
    : phase === "selected"
      ? "scale(1.35)"
      : phase === "dimmed"
        ? "scale(0.9)"
        : undefined;

  return (
    <button
      type="button"
      onClick={() => onSelect(profile)}
      disabled={disabled}
      aria-label={`Read as ${profile.name}`}
      className={cn(
        "group flex w-24 shrink-0 flex-col items-center gap-3 rounded-2xl p-2 outline-none sm:w-28",
        "focus-visible:ring-2 focus-visible:ring-primary/60",
        !reducedMotion && "transition-all duration-500 ease-out",
        phase === "selected" && "z-10",
        phase === "dimmed" && "opacity-20",
        phase === "dimmed" && !reducedMotion && "blur-[3px]",
        disabled && "cursor-default",
      )}
      style={{ ...entrance, transform }}
    >
      <span
        className={cn(
          "glass-panel rounded-2xl p-1.5 ring-2 ring-transparent transition-shadow",
          "group-hover:ring-primary/25 group-focus-visible:ring-primary/70",
          phase === "selected" && "ring-primary/80 shadow-glow",
        )}
      >
        <ProfileAvatar avatarKey={profile.avatar_key} size="xl" />
      </span>
      <span className="max-w-full truncate text-sm font-medium text-fg/90 group-hover:text-fg">
        {profile.name}
      </span>
    </button>
  );
}
