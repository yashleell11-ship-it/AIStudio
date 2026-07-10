"use client";

import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/types/api";
import { useContentPreferences, useSetMatureContent } from "../hooks";

export function MatureContentPanel() {
  const preferences = useContentPreferences();
  const mutation = useSetMatureContent();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enabled = preferences.data?.mature_content_enabled ?? false;
  const busy = preferences.isLoading || mutation.isPending;

  const apply = async (next: boolean) => {
    setError(null);
    try {
      await mutation.mutateAsync(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update this setting.");
    }
  };

  const handleToggle = (next: boolean) => {
    // Turning the gate ON requires an explicit age confirmation first;
    // turning it OFF is applied immediately.
    if (next) {
      setError(null);
      setConfirmOpen(true);
    } else {
      void apply(false);
    }
  };

  const confirmEnable = async () => {
    setConfirmOpen(false);
    await apply(true);
  };

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500/20 to-cyan-500/10 text-violet-400">
          <ShieldAlert className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-fg">Content</h2>
          <p className="mt-0.5 text-sm text-muted">
            Control whether adult (18+) content is shown across the app.
          </p>
        </div>
      </div>

      {preferences.isError ? (
        <div className="space-y-3">
          <p className="text-sm text-danger">
            {preferences.error instanceof ApiError
              ? preferences.error.message
              : "Failed to load content settings."}
          </p>
          <Button variant="secondary" onClick={() => preferences.refetch()}>
            Try again
          </Button>
        </div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-4 rounded-xl border border-border/40 bg-white/[0.02] px-4 py-3 transition-colors hover:border-violet-500/20">
            <div className="min-w-0">
              <p className="text-sm font-medium text-fg">Show mature (18+) content</p>
              <p className="mt-0.5 text-xs text-muted">
                Reveals adult sources, search results, and recommendations. Hidden by
                default — enabling requires confirming you are 18 or older.
              </p>
            </div>
            <Switch
              checked={enabled}
              onCheckedChange={handleToggle}
              disabled={busy}
              aria-label="Show mature (18+) content"
            />
          </div>

          {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
        </>
      )}

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Enable mature content?"
      >
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-warning/30 bg-warning/10 p-3">
            <ShieldAlert className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden />
            <p className="text-sm text-fg/90">
              This shows adult (18+) sources, search results, and recommendations
              throughout ManhwaManiacs. Only continue if you are of legal age to view
              mature content where you live. You can turn this off again at any time.
            </p>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button onClick={confirmEnable} disabled={mutation.isPending}>
              I am 18 or older — Enable
            </Button>
          </div>
        </div>
      </Dialog>
    </section>
  );
}
