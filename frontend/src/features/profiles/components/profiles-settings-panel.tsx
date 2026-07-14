"use client";

import { useState } from "react";
import { Check, Pencil, Plus, Trash2, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { useDeleteProfile, useProfiles } from "../hooks";
import { MOOD_LABELS } from "../mood";
import { useActiveProfileStore } from "../store";
import { MAX_PROFILES, type Profile } from "../types";
import { ProfileAvatar } from "./profile-avatar";
import { ProfileForm } from "./profile-form";

/**
 * Manage reading profiles (Settings → Profiles): create up to five, edit, and
 * delete. The active profile is badged; deleting it clears the selection so the
 * gate returns to the picker on the next navigation.
 */
export function ProfilesSettingsPanel() {
  const { data: profiles, isLoading, isError, error, refetch } = useProfiles();
  const deleteProfile = useDeleteProfile();
  const activeProfile = useActiveProfileStore((s) => s.activeProfile);
  const setActiveProfile = useActiveProfileStore((s) => s.setActiveProfile);

  const [formProfile, setFormProfile] = useState<Profile | undefined>(undefined);
  const [formOpen, setFormOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Profile | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const list = profiles ?? [];
  const atCapacity = list.length >= MAX_PROFILES;

  const openCreate = () => {
    setFormProfile(undefined);
    setFormOpen(true);
  };

  const openEdit = (profile: Profile) => {
    setFormProfile(profile);
    setFormOpen(true);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleteError(null);
    try {
      await deleteProfile.mutateAsync(pendingDelete.id);
      setPendingDelete(null);
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Could not delete this profile.");
    }
  };

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
            <Users className="size-5" aria-hidden />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-fg">Profiles</h2>
            <p className="mt-0.5 text-sm text-muted">
              Reading personas for this account — up to {MAX_PROFILES}. Each carries its own
              mood tint.
            </p>
          </div>
        </div>
        <Button size="sm" onClick={openCreate} disabled={atCapacity} className="shrink-0">
          <Plus className="size-4" aria-hidden />
          Add
        </Button>
      </div>

      {isError ? (
        <div className="space-y-3">
          <p className="text-sm text-danger">
            {error instanceof ApiError ? error.message : "Failed to load profiles."}
          </p>
          <Button variant="secondary" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : isLoading ? (
        <p className="text-sm text-muted">Loading profiles…</p>
      ) : list.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border/50 bg-white/[0.02] px-4 py-6 text-center text-sm text-muted">
          No profiles yet. Add one to get started.
        </p>
      ) : (
        <ul className="space-y-2">
          {list.map((profile) => {
            const isActive = activeProfile?.id === profile.id;
            return (
              <li
                key={profile.id}
                className={cn(
                  "flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors",
                  isActive
                    ? "border-primary/40 bg-primary/10"
                    : "border-border/40 bg-white/[0.02] hover:border-primary/20",
                )}
              >
                <ProfileAvatar avatarKey={profile.avatar_key} size="md" />
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 truncate text-sm font-medium text-fg">
                    {profile.name}
                    {isActive ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
                        <Check className="size-3" aria-hidden />
                        Active
                      </span>
                    ) : null}
                  </p>
                  <p className="truncate text-xs text-muted">{MOOD_LABELS[profile.mood]} mood</p>
                </div>
                {!isActive ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setActiveProfile(profile)}
                    className="text-muted hover:text-fg"
                  >
                    Use
                  </Button>
                ) : null}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => openEdit(profile)}
                  aria-label={`Edit ${profile.name}`}
                  className="text-muted hover:text-fg"
                >
                  <Pencil className="size-4" aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => {
                    setDeleteError(null);
                    setPendingDelete(profile);
                  }}
                  aria-label={`Delete ${profile.name}`}
                  className="text-muted hover:text-danger"
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </li>
            );
          })}
        </ul>
      )}

      {formOpen ? (
        <ProfileForm
          key={formProfile?.id ?? "new"}
          onClose={() => setFormOpen(false)}
          profile={formProfile}
        />
      ) : null}

      <Dialog
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="Delete profile?"
      >
        <div className="space-y-4">
          <p className="text-sm text-fg/90">
            Delete <span className="font-medium">{pendingDelete?.name}</span>? This removes the
            profile from this account. It cannot be undone.
          </p>
          {deleteError ? <p className="text-sm text-danger">{deleteError}</p> : null}
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              onClick={() => setPendingDelete(null)}
              disabled={deleteProfile.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={confirmDelete}
              disabled={deleteProfile.isPending}
            >
              {deleteProfile.isPending ? "Deleting…" : "Delete"}
            </Button>
          </div>
        </div>
      </Dialog>
    </section>
  );
}
