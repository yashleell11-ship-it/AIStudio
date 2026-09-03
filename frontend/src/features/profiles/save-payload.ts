import type { Mood } from "./mood";
import type { CreateProfilePayload, UpdateProfilePayload } from "./types";

/** What the create/edit dialog collects before saving. */
export interface ProfileFormValues {
  /** Already trimmed by the form. */
  name: string;
  avatarKey: string;
  mood: Mood;
  /** Per-profile 18+ gate (spec §3.7; settable at create/edit since 1a). */
  matureEnabled: boolean;
}

/**
 * Body for `POST /profiles`. `sort_order` is omitted on purpose — the backend
 * assigns the next slot.
 */
export function toCreateProfilePayload(
  values: ProfileFormValues,
): CreateProfilePayload {
  return {
    name: values.name,
    avatar_key: values.avatarKey,
    mood: values.mood,
    mature_content_enabled: values.matureEnabled,
  };
}

/**
 * Body for `PATCH /profiles/{id}`. Sends every form-owned field (the form is
 * always fully populated from the profile being edited); `sort_order` stays
 * out — reordering is not this dialog's job.
 */
export function toUpdateProfilePayload(
  values: ProfileFormValues,
): UpdateProfilePayload {
  return {
    name: values.name,
    avatar_key: values.avatarKey,
    mood: values.mood,
    mature_content_enabled: values.matureEnabled,
  };
}
