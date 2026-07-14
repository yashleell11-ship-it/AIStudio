export { ProfilePicker } from "./components/profile-picker";
export { ProfilesSettingsPanel } from "./components/profiles-settings-panel";
export { ProfileSwitcherChip } from "./components/profile-switcher-chip";
export { ProfileAvatar } from "./components/profile-avatar";
export { ProfileForm } from "./components/profile-form";
export {
  useProfiles,
  useCreateProfile,
  useUpdateProfile,
  useDeleteProfile,
  PROFILES_QUERY_KEY,
} from "./hooks";
export {
  useActiveProfileStore,
  getActiveProfileId,
} from "./store";
export {
  PROFILE_PICKER_PATH,
  isPickerPath,
  shouldRedirectToPicker,
  isProfileScopeError,
} from "./access";
export {
  MOODS,
  MOOD_LABELS,
  MOOD_TINT,
  MOOD_BASE,
  moodShellBackground,
  moodPickerBackground,
  moodAccent,
  isTintedMood,
  toMood,
} from "./mood";
export { AVATAR_PRESETS, DEFAULT_AVATAR_KEY, resolveAvatar } from "./avatars";
export type { Mood } from "./mood";
export type { AvatarPreset } from "./avatars";
export type {
  Profile,
  ActiveProfile,
  CreateProfilePayload,
  UpdateProfilePayload,
} from "./types";
export { MAX_PROFILES } from "./types";
