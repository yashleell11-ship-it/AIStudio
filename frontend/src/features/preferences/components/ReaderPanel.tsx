"use client";

import Link from "next/link";
import { BookOpenText } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { PROFILE_PICKER_PATH } from "@/features/profiles/access";
import { useActiveProfileStore } from "@/features/profiles/store";
import { useReaderSettings } from "@/features/reader/use-reader-settings";

/**
 * Reader chrome preferences (spec §3.3.1, §3.3.3).
 *
 * `pageGap` and `cinema` are stored per (user, profile) in scoped localStorage,
 * so — like the appearance panel — the toggles are disabled without an active
 * profile: a write with no scope is dropped and the switch would spring back.
 */
export function ReaderPanel() {
  const { pageGap, cinema, setPageGap, setCinema } = useReaderSettings();
  const hasProfile = useActiveProfileStore((state) => state.activeProfile !== null);

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
          <BookOpenText className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="font-display text-lg tracking-wide text-fg">Reader</h2>
          <p className="mt-0.5 text-sm text-muted">
            How the reading view behaves. Saved for this profile on this device.
          </p>
        </div>
      </div>

      {!hasProfile ? (
        <div className="mb-4 rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm text-fg">
          <p>
            No reading profile is active, so there is nowhere to save these
            choices yet.
          </p>
          <Link
            href={PROFILE_PICKER_PATH}
            className="mt-1 inline-block text-primary hover:underline"
          >
            Choose a profile
          </Link>
        </div>
      ) : null}

      <div className="space-y-3">
        <div className="flex items-start justify-between gap-4 rounded-xl border border-border bg-surface-2/40 px-4 py-3 transition-colors hover:border-primary/30">
          <div className="min-w-0">
            <p className="text-sm font-medium text-fg">Gap between pages</p>
            <p className="mt-0.5 text-xs text-muted">
              Off by default so a webtoon strip reads as one seamless image. Turn
              on for a thin separator between pages in continuous mode.
            </p>
          </div>
          <Switch
            checked={pageGap}
            onCheckedChange={setPageGap}
            disabled={!hasProfile}
            aria-label="Gap between pages"
          />
        </div>

        <div className="flex items-start justify-between gap-4 rounded-xl border border-border bg-surface-2/40 px-4 py-3 transition-colors hover:border-primary/30">
          <div className="min-w-0">
            <p className="text-sm font-medium text-fg">Cinema mode</p>
            <p className="mt-0.5 text-xs text-muted">
              Auto-hide every reader control after a few idle seconds; a tap,
              pointer move or the C key brings them back. Can also be toggled from
              inside the reader.
            </p>
          </div>
          <Switch
            checked={cinema}
            onCheckedChange={setCinema}
            disabled={!hasProfile}
            aria-label="Cinema mode"
          />
        </div>
      </div>
    </section>
  );
}
