"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Laptop, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatUtcDateTime } from "@/lib/utc-time";
import { cn } from "@/lib/cn";
import {
  describeAuthError,
  describeSessionDevice,
  sessionRowAction,
  sortSessionsForDisplay,
} from "../account-security";
import { useLogout, useRevokeSession, useSessions } from "../hooks";
import type { AccountSession } from "../types";

function SessionRow({
  session,
  busy,
  onRevoke,
  onSignOut,
}: {
  session: AccountSession;
  busy: boolean;
  onRevoke: (session: AccountSession) => void;
  onSignOut: () => void;
}) {
  const action = sessionRowAction(session);
  const isCurrent = action === "sign-out-current";

  return (
    <li
      className={cn(
        "flex flex-wrap items-start justify-between gap-3 rounded-xl border p-4",
        isCurrent
          ? "border-primary/40 bg-primary/[0.07]"
          : "border-border bg-surface-2/40",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-fg">
            {describeSessionDevice(session.user_agent)}
          </p>
          {isCurrent ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-primary/40 bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
              <Laptop className="size-3" aria-hidden />
              This device
            </span>
          ) : null}
        </div>
        <p className="mt-1 text-xs text-muted">
          Last used {formatUtcDateTime(session.last_used_at, { missing: "unknown" })}
          {session.ip_address ? ` · ${session.ip_address}` : ""}
        </p>
        <p className="mt-0.5 text-xs text-muted">
          Signed in {formatUtcDateTime(session.created_at, { missing: "unknown" })} · expires{" "}
          {formatUtcDateTime(session.expires_at, { missing: "unknown" })}
        </p>
      </div>

      {isCurrent ? (
        <Button variant="secondary" size="sm" onClick={onSignOut} disabled={busy}>
          Sign out
        </Button>
      ) : (
        <Button
          variant="danger"
          size="sm"
          onClick={() => onRevoke(session)}
          disabled={busy}
        >
          Revoke
        </Button>
      )}
    </li>
  );
}

/**
 * Every live session on this account, this device first and clearly marked.
 *
 * The current row is deliberately not revocable: `DELETE /auth/sessions/{id}`
 * accepts the caller's own id and would leave the tab holding a dead cookie
 * with no explanation, so that row offers the ordinary sign-out instead, which
 * clears the cache and lands on /login.
 */
export function SessionList() {
  const router = useRouter();
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const logout = useLogout();
  const [error, setError] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<number | null>(null);

  const handleRevoke = async (session: AccountSession) => {
    setError(null);
    setRevokingId(session.id);
    try {
      await revoke.mutateAsync(session.id);
    } catch (failure) {
      setError(describeAuthError(failure, "Could not revoke that session. Please try again."));
    } finally {
      setRevokingId(null);
    }
  };

  const handleSignOut = async () => {
    try {
      await logout.mutateAsync();
    } catch {
      // `useLogout.onSettled` clears the session locally either way.
    }
    router.replace("/login");
  };

  if (sessions.isPending) {
    return <p className="text-sm text-muted">Loading sessions…</p>;
  }

  if (sessions.isError) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-danger">
          {describeAuthError(sessions.error, "Could not load your sessions.")}
        </p>
        <Button variant="secondary" size="sm" onClick={() => sessions.refetch()}>
          <RefreshCw className="size-4" aria-hidden />
          Try again
        </Button>
      </div>
    );
  }

  const rows = sortSessionsForDisplay(sessions.data);

  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {rows.map((session) => (
          <SessionRow
            key={session.id}
            session={session}
            busy={revokingId === session.id || logout.isPending}
            onRevoke={handleRevoke}
            onSignOut={handleSignOut}
          />
        ))}
      </ul>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      <Button
        variant="ghost"
        size="sm"
        onClick={() => sessions.refetch()}
        disabled={sessions.isFetching}
      >
        <RefreshCw className={cn("size-4", sessions.isFetching && "animate-spin")} aria-hidden />
        {sessions.isFetching ? "Refreshing…" : "Refresh"}
      </Button>
    </div>
  );
}
