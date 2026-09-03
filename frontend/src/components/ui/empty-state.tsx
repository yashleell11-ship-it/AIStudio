import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Button, type ButtonProps } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export interface EmptyStateAction {
  label: string;
  href?: string;
  onClick?: () => void;
  icon?: LucideIcon;
  disabled?: boolean;
  variant?: ButtonProps["variant"];
}

export type EmptyStateTone = "empty" | "error" | "offline";

export interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  /** The one thing worth doing next. Rendered as a real button, not a hint. */
  action?: EmptyStateAction;
  secondaryAction?: EmptyStateAction;
  /**
   * "empty" (default, amber) — nothing here yet.
   * "error" (red) — the request failed; pair with a "Try again" `action`.
   * "offline" (yellow) — the server could not be reached at all; pair with an
   * `action` that points at what still works without one (e.g. Downloads).
   */
  tone?: EmptyStateTone;
  className?: string;
}

const ICON_TONE: Record<EmptyStateTone, string> = {
  empty: "bg-primary/10 text-primary",
  error: "bg-danger/10 text-danger",
  offline: "bg-warning/10 text-warning",
};

const DEFAULT_ACTION_VARIANT: Record<EmptyStateTone, NonNullable<ButtonProps["variant"]>> = {
  empty: "primary",
  error: "secondary",
  offline: "secondary",
};

function ActionButton({ action, tone }: { action: EmptyStateAction; tone: EmptyStateTone }) {
  const Icon = action.icon;
  const variant = action.variant ?? DEFAULT_ACTION_VARIANT[tone];
  const content = (
    <>
      {Icon ? <Icon className="size-4" aria-hidden /> : null}
      {action.label}
    </>
  );
  if (action.href) {
    return (
      <Link href={action.href}>
        <Button variant={variant} disabled={action.disabled}>
          {content}
        </Button>
      </Link>
    );
  }
  return (
    <Button variant={variant} onClick={action.onClick} disabled={action.disabled}>
      {content}
    </Button>
  );
}

/**
 * The one "nothing to show" card for the app: an icon, a plain-language
 * title, a description, and — almost always — a single real action to take
 * next. Never a bare "no items yet".
 *
 * Built once so a screen never re-invents its own dashed box: reuses the
 * `.empty-state` panel (globals.css) that the app's best existing empty
 * states (the followed-library shelf, Collections) already established, so
 * adopting this component is a consolidation, not a restyle.
 *
 * `tone` doubles as the "empty vs. couldn't load vs. offline" signal from
 * `resolveViewState` (`lib/view-state.ts`) — pass it straight through so the
 * icon colour and the default action wording match what actually happened.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  tone = "empty",
  className,
}: EmptyStateProps) {
  return (
    <div className={cn("empty-state", className)}>
      <div
        className={cn(
          "mx-auto mb-4 flex size-14 items-center justify-center rounded-full",
          ICON_TONE[tone],
        )}
      >
        <Icon className="size-7" aria-hidden />
      </div>
      <p className="text-lg font-medium text-fg">{title}</p>
      {description ? (
        <p className="mx-auto mt-2 max-w-md text-sm text-muted">{description}</p>
      ) : null}
      {action || secondaryAction ? (
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          {action ? <ActionButton action={action} tone={tone} /> : null}
          {secondaryAction ? <ActionButton action={secondaryAction} tone={tone} /> : null}
        </div>
      ) : null}
    </div>
  );
}
