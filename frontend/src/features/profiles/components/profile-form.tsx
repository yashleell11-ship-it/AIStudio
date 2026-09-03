"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { AVATAR_PRESETS, resolveAvatar } from "../avatars";
import { useCreateProfile, useUpdateProfile } from "../hooks";
import { MOODS, MOOD_LABELS, MOOD_TINT, isTintedMood, type Mood } from "../mood";
import { toCreateProfilePayload, toUpdateProfilePayload } from "../save-payload";
import type { Profile } from "../types";
import { ProfileAvatar } from "./profile-avatar";

interface ProfileFormProps {
  onClose: () => void;
  /** Present → edit that profile; absent → create a new one. */
  profile?: Profile;
  /** Called with the created/updated profile after a successful save. */
  onSaved?: (profile: Profile) => void;
}

const MAX_NAME = 30;

/**
 * Create or edit a reading profile: name, avatar, and mood. A single dialog
 * backs both the picker's "add profile" tile and the Settings management panel.
 *
 * The form is always rendered "open"; callers mount it only while it should be
 * visible (and pass a `key` to re-seed when switching targets), so the fields
 * initialise straight from `profile` with no reset effect.
 */
export function ProfileForm({ onClose, profile, onSaved }: ProfileFormProps) {
  const editing = Boolean(profile);
  const create = useCreateProfile();
  const update = useUpdateProfile();

  const [name, setName] = useState(() => profile?.name ?? "");
  const [avatarKey, setAvatarKey] = useState<string>(
    () => resolveAvatar(profile?.avatar_key).key,
  );
  const [mood, setMood] = useState<Mood>(() => profile?.mood ?? "default");
  const [matureEnabled, setMatureEnabled] = useState(
    () => profile?.mature_content_enabled ?? false,
  );
  const [error, setError] = useState<string | null>(null);

  const saving = create.isPending || update.isPending;
  const trimmed = name.trim();

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!trimmed || saving) return;
    setError(null);
    try {
      const values = {
        name: trimmed,
        avatarKey,
        mood,
        matureEnabled,
      };
      const saved = profile
        ? await update.mutateAsync({
            id: profile.id,
            changes: toUpdateProfilePayload(values),
          })
        : await create.mutateAsync(toCreateProfilePayload(values));
      onSaved?.(saved);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save this profile.");
    }
  };

  return (
    <Dialog open onClose={onClose} title={editing ? "Edit profile" : "Add profile"}>
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="flex items-center gap-4">
          <ProfileAvatar avatarKey={avatarKey} size="lg" />
          <div className="min-w-0 flex-1">
            <label htmlFor="profile-name" className="mb-1.5 block text-sm font-medium text-fg">
              Name
            </label>
            <Input
              id="profile-name"
              value={name}
              onChange={(event) => setName(event.target.value.slice(0, MAX_NAME))}
              placeholder="e.g. Late-night reads"
              maxLength={MAX_NAME}
              autoComplete="off"
              autoFocus
            />
          </div>
        </div>

        <fieldset>
          <legend className="mb-2 text-sm font-medium text-fg">Avatar</legend>
          <div className="grid grid-cols-6 gap-2">
            {AVATAR_PRESETS.map((preset) => {
              const selected = preset.key === avatarKey;
              return (
                <button
                  key={preset.key}
                  type="button"
                  onClick={() => setAvatarKey(preset.key)}
                  aria-pressed={selected}
                  aria-label={preset.label}
                  title={preset.label}
                  className={cn(
                    "flex items-center justify-center rounded-xl p-0.5 transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                    selected
                      ? "ring-2 ring-primary ring-offset-2 ring-offset-panel"
                      : "opacity-70 hover:opacity-100",
                  )}
                >
                  <ProfileAvatar avatarKey={preset.key} size="sm" />
                </button>
              );
            })}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-sm font-medium text-fg">Mood tint</legend>
          <p className="mb-2 text-xs text-muted">
            Tints the app background while this profile is active — never the reader.
          </p>
          <div className="flex flex-wrap gap-2">
            {MOODS.map((value) => {
              const selected = value === mood;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => setMood(value)}
                  aria-pressed={selected}
                  className={cn(
                    "flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                    selected
                      ? "border-primary/60 bg-primary/15 text-fg"
                      : "border-border/50 text-muted hover:border-primary/30 hover:text-fg",
                  )}
                >
                  <span
                    className="size-3 rounded-full border border-white/10"
                    style={{
                      background: isTintedMood(value) ? MOOD_TINT[value] : "#1c1917",
                    }}
                    aria-hidden
                  />
                  {MOOD_LABELS[value]}
                </button>
              );
            })}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-sm font-medium text-fg">
            Mature content
          </legend>
          <div className="flex items-start justify-between gap-4 rounded-xl border border-border/50 px-3 py-2.5">
            <div className="min-w-0">
              <p className="text-sm font-medium text-fg">
                Show mature (18+) content
              </p>
              <p className="mt-0.5 text-xs text-muted">
                Lets this profile see 18+ sources and series. Confirm you are of
                legal age where you live.
              </p>
            </div>
            <Switch
              checked={matureEnabled}
              onCheckedChange={setMatureEnabled}
              aria-label="Show mature (18+) content for this profile"
            />
          </div>
        </fieldset>

        {error ? <p className="text-sm text-danger">{error}</p> : null}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" disabled={!trimmed || saving}>
            {saving ? "Saving…" : editing ? "Save changes" : "Create profile"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
