"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, LogOut, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/cn";
import { useCurrentUser, useLogout } from "../hooks";

function initials(label: string): string {
  const words = label.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[1][0]}`.toUpperCase();
}

/** Topbar account control: shows the signed-in user and a sign-out action. */
export function UserMenu() {
  const router = useRouter();
  const { data: user } = useCurrentUser();
  const logout = useLogout();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!user) return null;

  const label = user.display_name?.trim() || user.username;

  const handleLogout = async () => {
    setOpen(false);
    try {
      await logout.mutateAsync();
    } catch {
      // The session is cleared locally in `useLogout.onSettled` regardless.
    }
    router.replace("/login");
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      >
        <span
          className="flex size-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary to-accent text-xs font-semibold text-white"
          aria-hidden
        >
          {initials(label)}
        </span>
        <span className="hidden max-w-[10rem] truncate text-sm text-fg sm:block">{label}</span>
        <ChevronDown
          className={cn("size-4 shrink-0 transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="Account"
          className="glass-panel absolute right-0 top-full z-50 mt-2 w-60 overflow-hidden rounded-xl border border-border/50 shadow-glass"
        >
          <div className="border-b border-border/50 px-4 py-3">
            <p className="truncate font-medium text-fg">{label}</p>
            <p className="truncate text-xs text-muted">@{user.username}</p>
            {user.email ? (
              <p className="mt-0.5 truncate text-xs text-muted">{user.email}</p>
            ) : null}
            {user.is_admin ? (
              <span className="mt-2 inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
                <ShieldCheck className="size-3" aria-hidden />
                Administrator
              </span>
            ) : null}
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            disabled={logout.isPending}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm text-muted transition-colors hover:bg-white/5 hover:text-fg disabled:pointer-events-none disabled:opacity-50"
          >
            <LogOut className="size-4" aria-hidden />
            {logout.isPending ? "Signing out…" : "Sign out"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
