"use client";

import { useEffect, useId, useRef } from "react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}

const FOCUSABLE =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export function Dialog({ open, onClose, title, children, className }: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  // Per-instance: a fixed "dialog-title" id collides the moment two dialogs are
  // mounted at once (a confirm inside a sheet), and duplicate ids make
  // `aria-labelledby` point at whichever the browser found first.
  const titleId = useId();

  useEffect(() => {
    if (!open) return;

    previousFocusRef.current = document.activeElement as HTMLElement | null;

    const panel = panelRef.current;
    const focusable = panel?.querySelectorAll<HTMLElement>(FOCUSABLE);
    const first = focusable?.[0];
    requestAnimationFrame(() => first?.focus());

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !focusable?.length) return;

      const firstEl = focusable[0];
      const lastEl = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === firstEl) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && document.activeElement === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Click-outside target only. Hidden from assistive tech and out of the
          tab order: announcing a full-screen "Close dialog" button before the
          dialog's own content is noise, and Escape plus the Close button below
          already give keyboard and screen-reader users the same way out. */}
      <button
        type="button"
        aria-hidden
        tabIndex={-1}
        className="absolute inset-0 bg-bg/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          "glass-panel relative z-10 w-full max-w-lg rounded-2xl border border-border/50 p-6 shadow-glass",
          className,
        )}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id={titleId} className="text-lg font-semibold text-fg">
            {title}
          </h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            ×
          </Button>
        </div>
        {children}
      </div>
    </div>
  );
}
