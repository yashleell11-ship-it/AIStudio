import type { Mood } from "./mood";

/**
 * Contracts for the backend profiles surface (routes under `/profiles`).
 * A profile is a per-user reading persona (Netflix-style); every request rides
 * the `mm_session` cookie like the rest of the authenticated API.
 */

export interface Profile {
  id: number;
  name: string;
  /** References an avatar in `avatars.ts`; may be null for legacy rows. */
  avatar_key: string | null;
  mood: Mood;
  sort_order: number;
  /** Per-profile 18+ gate. Settable at create/edit since 1a. */
  mature_content_enabled: boolean;
  created_at: string;
}

export interface CreateProfilePayload {
  name: string;
  avatar_key: string;
  mood: Mood;
  /** Optional; the backend assigns an order when omitted. */
  sort_order?: number;
  mature_content_enabled?: boolean;
}

export type UpdateProfilePayload = Partial<{
  name: string;
  avatar_key: string;
  mood: Mood;
  sort_order: number;
  mature_content_enabled: boolean;
}>;

/**
 * The minimal snapshot of the active profile kept in client state (persisted to
 * localStorage). Enough to tint the shell and label the switcher without
 * re-fetching the list on every page.
 */
export interface ActiveProfile {
  id: number;
  name: string;
  avatar_key: string | null;
  mood: Mood;
}

/** Hard cap on profiles per account, enforced in the UI. */
export const MAX_PROFILES = 5;
