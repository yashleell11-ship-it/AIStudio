import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface PrimaryPillButtonProps {
  /** Text label. Ignored when `children` is provided. */
  label?: string;
  /** When set, renders a Next.js `Link` instead of a `<button>`. */
  href?: string;
  onClick?: () => void;
  className?: string;
  /** Optional leading icon node. */
  icon?: ReactNode;
  disabled?: boolean;
  /** Overrides `label` when present. */
  children?: ReactNode;
}

const pillClasses =
  "inline-flex items-center justify-center gap-2 rounded-full px-7 py-3 font-medium uppercase tracking-wide text-white cta-gradient transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:pointer-events-none disabled:opacity-50";

export function PrimaryPillButton({
  label = "Continue Reading",
  href,
  onClick,
  className,
  icon,
  disabled = false,
  children,
}: PrimaryPillButtonProps) {
  const content = (
    <>
      {icon}
      <span>{children ?? label}</span>
    </>
  );

  if (href && !disabled) {
    return (
      <Link href={href} onClick={onClick} className={cn(pillClasses, className)}>
        {content}
      </Link>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-disabled={disabled || undefined}
      className={cn(pillClasses, className)}
    >
      {content}
    </button>
  );
}
