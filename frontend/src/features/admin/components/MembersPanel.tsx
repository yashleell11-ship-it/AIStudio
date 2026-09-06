"use client";

import { useState } from "react";
import { RefreshCw, Trash2, TriangleAlert, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useCurrentUser } from "@/features/auth/hooks";
import { cn } from "@/lib/cn";
import { formatUtcDate, formatUtcDateTime } from "@/lib/utc-time";
import { useDeleteMember, useMembers, useSetMemberActive } from "../hooks";
import {
  activeToggleLabel,
  deleteMemberConfirmation,
  describeMembersFailure,
  describeOtherMembers,
  formatSessionCount,
  memberRowGuard,
  shapeMemberRows,
} from "../members";
import type { MemberAccount } from "../types";

function HeaderCell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-widest text-muted",
        className,
      )}
    >
      {children}
    </th>
  );
}

function ActiveBadge({ active }: { active: boolean }) {
  return active ? (
    <Badge variant="success">Active</Badge>
  ) : (
    <Badge className="border-danger/30 bg-danger/15 text-danger">Deactivated</Badge>
  );
}

function MemberTableRow({
  member,
  currentUserId,
  busy,
  onToggleActive,
  onDelete,
}: {
  member: MemberAccount;
  currentUserId: number | null | undefined;
  busy: boolean;
  onToggleActive: (member: MemberAccount) => void;
  onDelete: (member: MemberAccount) => void;
}) {
  const guard = memberRowGuard(member, currentUserId);
  const toggleLabel = activeToggleLabel(member.is_active);

  return (
    <tr
      className={cn(
        "border-t border-border/30",
        guard.isSelf ? "bg-primary/[0.05]" : "hover:bg-white/[0.02]",
      )}
    >
      <td className="px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-fg">{member.username}</span>
          {member.is_admin ? <Badge variant="primary">Admin</Badge> : null}
          {guard.isSelf ? <Badge>You</Badge> : null}
        </div>
      </td>
      <td className="px-3 py-2.5">
        <ActiveBadge active={member.is_active} />
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-muted">
        {formatUtcDate(member.created_at, { missing: "Unknown", invalid: "Unknown" })}
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-muted">
        {formatUtcDateTime(member.last_login_at)}
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-muted">
        {formatSessionCount(member.session_count)}
      </td>
      <td className="px-3 py-2.5">
        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onToggleActive(member)}
            disabled={!guard.canToggleActive || busy}
            title={guard.reason ?? undefined}
            aria-label={`${toggleLabel} ${member.username}`}
          >
            {toggleLabel}
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => onDelete(member)}
            disabled={!guard.canDelete || busy}
            title={guard.reason ?? undefined}
            aria-label={`Delete ${member.username}`}
          >
            <Trash2 className="size-4" aria-hidden />
            Delete
          </Button>
        </div>
      </td>
    </tr>
  );
}

/**
 * Every account on this server, with the owner's two controls over each:
 * switch it off (reversible) or delete it (not).
 *
 * Admin-only, because the endpoints are and because registration on this
 * instance is open by choice — this table is how the owner finds out who took
 * it up. The settings page already gates the mount on `is_admin`, and the
 * panel checks again here: a component that lists every account must not
 * depend on its caller remembering to.
 *
 * The caller's own row is shown but inert. The server answers 400 to an admin
 * targeting themselves; disabling the buttons says so before the click rather
 * than after it (see `memberRowGuard`).
 */
export function MembersPanel() {
  const { data: user } = useCurrentUser();
  const isAdmin = user?.is_admin ?? false;
  const members = useMembers(isAdmin);
  const setActive = useSetMemberActive();
  const deleteMember = useDeleteMember();

  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<MemberAccount | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (!isAdmin) return null;

  const handleToggleActive = async (member: MemberAccount) => {
    setActionError(null);
    setBusyId(member.id);
    try {
      await setActive.mutateAsync({ userId: member.id, isActive: !member.is_active });
    } catch (failure) {
      const verb = member.is_active ? "deactivate" : "reactivate";
      setActionError(
        describeMembersFailure(failure, `Could not ${verb} ${member.username}. Please try again.`),
      );
    } finally {
      setBusyId(null);
    }
  };

  const openDelete = (member: MemberAccount) => {
    setActionError(null);
    setDeleteError(null);
    setPendingDelete(member);
  };

  const closeDelete = () => {
    // Escape and the backdrop route through here too; a dialog that vanishes
    // mid-request would leave its failure with nowhere to be read.
    if (deleteMember.isPending) return;
    setPendingDelete(null);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleteError(null);
    try {
      await deleteMember.mutateAsync(pendingDelete.id);
      setPendingDelete(null);
    } catch (failure) {
      setDeleteError(
        describeMembersFailure(
          failure,
          `Could not delete ${pendingDelete.username}. Please try again.`,
        ),
      );
    }
  };

  const rows = shapeMemberRows(members.data ?? [], user?.id);
  const confirmation = pendingDelete ? deleteMemberConfirmation(pendingDelete) : null;

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
          <Users className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="font-display text-lg tracking-wide text-fg">Members</h2>
          <p className="mt-0.5 text-sm text-muted">
            Everyone with an account on this server.
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-border/40 bg-white/[0.02] p-4">
        <p className="text-sm text-fg/90">
          Registration is open, so anyone who signs up appears here. Deactivating
          an account keeps it and its data but refuses sign-in until it is
          reactivated. Deleting removes the account and everything it owns, for
          good.
        </p>

        {members.isPending ? (
          <div className="mt-4 space-y-2" aria-busy="true">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="h-10 animate-pulse rounded-lg bg-surface-2" />
            ))}
          </div>
        ) : members.isError ? (
          <div className="mt-4 space-y-3">
            <p role="alert" className="text-sm text-danger">
              {describeMembersFailure(members.error, "Could not load the member list.")}
            </p>
            <Button variant="secondary" size="sm" onClick={() => members.refetch()}>
              <RefreshCw className="size-4" aria-hidden />
              Try again
            </Button>
          </div>
        ) : rows.length === 0 ? (
          <p className="mt-4 rounded-lg border border-dashed border-border/50 px-3 py-2.5 text-xs leading-relaxed text-muted">
            No accounts to show. Anyone who registers appears here.
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto rounded-lg border border-border/30">
            <table className="w-full min-w-[40rem] text-sm">
              <thead className="bg-white/[0.03]">
                <tr>
                  <HeaderCell>Member</HeaderCell>
                  <HeaderCell>Status</HeaderCell>
                  <HeaderCell>Joined</HeaderCell>
                  <HeaderCell>Last seen</HeaderCell>
                  <HeaderCell>Sessions</HeaderCell>
                  <HeaderCell className="text-right">
                    <span className="sr-only">Actions</span>
                  </HeaderCell>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ member }) => (
                  <MemberTableRow
                    key={member.id}
                    member={member}
                    currentUserId={user?.id}
                    busy={
                      busyId === member.id ||
                      (deleteMember.isPending && pendingDelete?.id === member.id)
                    }
                    onToggleActive={handleToggleActive}
                    onDelete={openDelete}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {actionError ? (
          <p role="alert" className="mt-3 text-sm text-danger">
            {actionError}
          </p>
        ) : null}

        {members.isSuccess ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-muted">{describeOtherMembers(rows)}</p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => members.refetch()}
              disabled={members.isFetching}
            >
              <RefreshCw
                className={cn("size-4", members.isFetching && "animate-spin")}
                aria-hidden
              />
              {members.isFetching ? "Refreshing…" : "Refresh"}
            </Button>
          </div>
        ) : null}
      </div>

      <Dialog
        open={pendingDelete !== null}
        onClose={closeDelete}
        title={confirmation?.title ?? "Delete account?"}
      >
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-danger/30 bg-danger/10 p-3">
            <TriangleAlert className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden />
            <p className="text-sm text-fg/90">{confirmation?.body}</p>
          </div>

          {deleteError ? (
            <p role="alert" className="text-sm text-danger">
              {deleteError}
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={closeDelete} disabled={deleteMember.isPending}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={confirmDelete}
              disabled={deleteMember.isPending}
            >
              {deleteMember.isPending ? "Deleting…" : confirmation?.action ?? "Delete"}
            </Button>
          </div>
        </div>
      </Dialog>
    </section>
  );
}
