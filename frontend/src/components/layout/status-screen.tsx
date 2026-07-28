import type { ReactNode } from "react";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { cn } from "@/lib/cn";

export interface StatusScreenProps {
  /** Big display glyph behind the heading — "404", "500", an emoji, anything short. */
  code: string;
  title: string;
  description: ReactNode;
  /** Primary and secondary controls, already rendered (pill buttons, links). */
  actions?: ReactNode;
  /** Extra detail under the actions — an error digest, a stack hint. */
  footnote?: ReactNode;
  className?: string;
}

/**
 * The look for a page that cannot show what was asked for: 404, a thrown render
 * error, and the last-resort root error boundary all use it.
 *
 * Built from the existing design language rather than a new one — Syne display
 * face, the bronze→cream `HeroHeading` gradient, the warm glow — so a dead end
 * still reads as part of the app instead of as the framework's default black
 * page with a monospace stack trace.
 *
 * Deliberately hook-free so it can render from a Server Component (`not-found`)
 * and from a Client Component (`error`) without a second implementation.
 */
export function StatusScreen({
  code,
  title,
  description,
  actions,
  footnote,
  className,
}: StatusScreenProps) {
  return (
    <div
      className={cn(
        "relative flex min-h-full flex-col items-center justify-center overflow-hidden px-6 py-24 text-center",
        className,
      )}
    >
      {/* Warm eclipse behind the code. Purely decorative. */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/2 -z-10 size-[36rem] max-w-[120vw] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-60 blur-3xl"
        style={{
          background:
            "radial-gradient(circle, color-mix(in srgb, var(--color-primary) 18%, transparent) 0%, transparent 70%)",
        }}
      />

      <p
        aria-hidden
        className="font-display text-[clamp(5rem,22vw,13rem)] font-black leading-none tracking-tighter text-fg/[0.07]"
      >
        {code}
      </p>

      <div className="-mt-[0.35em]">
        <HeroHeading className="text-[clamp(2rem,6vw,3.5rem)]">{title}</HeroHeading>
      </div>

      <div className="mt-4 max-w-md text-sm leading-relaxed text-muted">
        {description}
      </div>

      {actions ? (
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          {actions}
        </div>
      ) : null}

      {footnote ? (
        <div className="mt-8 max-w-md text-xs text-muted">{footnote}</div>
      ) : null}
    </div>
  );
}
