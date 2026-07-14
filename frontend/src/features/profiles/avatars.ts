import {
  BookOpen,
  Cat,
  Coffee,
  Flame,
  Ghost,
  Heart,
  Moon,
  Rocket,
  Sparkles,
  Star,
  Sword,
  Wand2,
  type LucideIcon,
} from "lucide-react";

/**
 * The fixed catalogue of profile avatars. `avatar_key` on a profile references
 * one of these by `key`; each pairs a lucide glyph with a gradient so avatars
 * read as distinct coloured tiles (Netflix-style) rather than plain initials.
 * Adding an avatar means adding an entry here — the one place avatars live.
 */
export interface AvatarPreset {
  key: string;
  label: string;
  icon: LucideIcon;
  /** Tailwind gradient classes for the circular tile background. */
  gradient: string;
}

export const AVATAR_PRESETS: readonly AvatarPreset[] = [
  { key: "violet", label: "Violet Spark", icon: Sparkles, gradient: "from-violet-500 to-fuchsia-500" },
  { key: "cyan", label: "Cyan Rocket", icon: Rocket, gradient: "from-cyan-500 to-sky-500" },
  { key: "rose", label: "Rose Heart", icon: Heart, gradient: "from-rose-500 to-pink-500" },
  { key: "amber", label: "Amber Coffee", icon: Coffee, gradient: "from-amber-500 to-orange-500" },
  { key: "emerald", label: "Emerald Cat", icon: Cat, gradient: "from-emerald-500 to-teal-500" },
  { key: "ember", label: "Ember Flame", icon: Flame, gradient: "from-red-500 to-amber-500" },
  { key: "blade", label: "Steel Blade", icon: Sword, gradient: "from-slate-400 to-slate-600" },
  { key: "phantom", label: "Phantom", icon: Ghost, gradient: "from-indigo-500 to-slate-700" },
  { key: "arcane", label: "Arcane Wand", icon: Wand2, gradient: "from-purple-500 to-indigo-500" },
  { key: "lunar", label: "Lunar Moon", icon: Moon, gradient: "from-sky-600 to-indigo-700" },
  { key: "star", label: "Starlight", icon: Star, gradient: "from-yellow-400 to-amber-500" },
  { key: "reader", label: "Bookworm", icon: BookOpen, gradient: "from-teal-500 to-cyan-600" },
] as const;

/** The avatar shown when a profile has no (or an unknown) `avatar_key`. */
export const DEFAULT_AVATAR_KEY = AVATAR_PRESETS[0].key;

/** Resolve an `avatar_key` to its preset, falling back to the default avatar. */
export function resolveAvatar(avatarKey: string | null | undefined): AvatarPreset {
  return (
    AVATAR_PRESETS.find((preset) => preset.key === avatarKey) ?? AVATAR_PRESETS[0]
  );
}
