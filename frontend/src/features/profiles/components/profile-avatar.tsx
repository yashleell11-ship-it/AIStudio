import { cn } from "@/lib/cn";
import { resolveAvatar } from "../avatars";

type AvatarSize = "sm" | "md" | "lg" | "xl";

const SIZES: Record<AvatarSize, { box: string; icon: string }> = {
  sm: { box: "size-8", icon: "size-4" },
  md: { box: "size-11", icon: "size-5" },
  lg: { box: "size-20", icon: "size-9" },
  xl: { box: "size-28 md:size-32", icon: "size-12 md:size-14" },
};

interface ProfileAvatarProps {
  avatarKey: string | null | undefined;
  size?: AvatarSize;
  className?: string;
}

/**
 * The coloured, glyphed avatar tile for a profile. Presentation-only: the
 * avatar is resolved from `avatar_key` via the shared avatar catalogue so the
 * same visual is reused by the picker, switcher chip, and management panel.
 */
export function ProfileAvatar({ avatarKey, size = "md", className }: ProfileAvatarProps) {
  const preset = resolveAvatar(avatarKey);
  const Icon = preset.icon;
  const dims = SIZES[size];

  return (
    <span
      className={cn(
        "flex items-center justify-center rounded-2xl bg-gradient-to-br text-white shadow-glass",
        preset.gradient,
        dims.box,
        className,
      )}
      aria-hidden
    >
      <Icon className={dims.icon} />
    </span>
  );
}
