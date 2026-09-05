"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, ShieldCheck, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { canSignOutEverywhere, describeAuthError } from "../account-security";
import { useLogoutAll } from "../hooks";
import { ChangePasswordForm } from "./change-password-form";
import { SessionList } from "./session-list";

/**
 * The account's own security settings: rotate the password, see where the
 * account is signed in, and sign out everywhere.
 *
 * Per-reader, not admin — every account has a password and sessions of its
 * own, which is why this sits alongside the reader's other preferences rather
 * than behind `is_admin`.
 */
export function AccountSecurityPanel() {
  const router = useRouter();
  const logoutAll = useLogoutAll();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openConfirm = () => {
    setError(null);
    // Reset every time: an acknowledgement carried over from a dialog the user
    // dismissed would make the next open one click from signing them out.
    setAcknowledged(false);
    setConfirmOpen(true);
  };

  const handleSignOutEverywhere = async () => {
    if (!canSignOutEverywhere(acknowledged, logoutAll.isPending)) return;
    try {
      await logoutAll.mutateAsync();
    } catch (failure) {
      // Nothing was revoked, and `useLogoutAll` leaves the local session alone
      // on failure precisely so this message survives to be read — a redirect
      // here would tell the user "everywhere" about a call that never landed.
      setError(describeAuthError(failure, "Could not sign out everywhere. Please try again."));
      setConfirmOpen(false);
      return;
    }
    setConfirmOpen(false);
    router.replace("/login");
  };

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
          <ShieldCheck className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="font-display text-lg tracking-wide text-fg">Security</h2>
          <p className="mt-0.5 text-sm text-muted">
            Change your password and manage the devices signed in to this account.
          </p>
        </div>
      </div>

      <div className="space-y-8">
        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
            Password
          </h3>
          <ChangePasswordForm />
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
            Active sessions
          </h3>
          <SessionList />
        </div>

        <div className="rounded-xl border border-danger/30 bg-danger/[0.06] p-4">
          <div className="flex items-start gap-3">
            <TriangleAlert className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden />
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-fg">Sign out everywhere</h3>
              <p className="mt-0.5 text-xs text-muted">
                Revokes every session on this account, including this one. Use it if you
                think someone else has your password — then change it.
              </p>
              {error ? (
                <p role="alert" className="mt-2 text-sm text-danger">
                  {error}
                </p>
              ) : null}
              <Button
                variant="danger"
                size="sm"
                className="mt-3"
                onClick={openConfirm}
                disabled={logoutAll.isPending}
              >
                <LogOut className="size-4" aria-hidden />
                Sign out everywhere
              </Button>
            </div>
          </div>
        </div>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Sign out everywhere?"
      >
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-danger/30 bg-danger/10 p-3">
            <TriangleAlert className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden />
            <p className="text-sm text-fg/90">
              Every device signed in to this account is signed out — phones, other
              browsers, and this one. You will be sent back to the sign-in screen and
              will need your password to get back in.
            </p>
          </div>

          <div className="flex items-start justify-between gap-4">
            <label htmlFor="confirm-sign-out-everywhere" className="text-sm text-muted">
              I understand this signs me out on this device too
            </label>
            <Switch
              id="confirm-sign-out-everywhere"
              checked={acknowledged}
              onCheckedChange={setAcknowledged}
              disabled={logoutAll.isPending}
              aria-label="I understand this signs me out on this device too"
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleSignOutEverywhere}
              disabled={!canSignOutEverywhere(acknowledged, logoutAll.isPending)}
            >
              {logoutAll.isPending ? "Signing out…" : "Sign out everywhere"}
            </Button>
          </div>
        </div>
      </Dialog>
    </section>
  );
}
