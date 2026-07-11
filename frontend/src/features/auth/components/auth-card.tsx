import type { ReactNode } from "react";

interface AuthCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * The centered, full-height frame shared by every auth screen. It owns its own
 * scroll (the app body is `overflow: hidden`) so tall forms remain reachable on
 * short viewports.
 */
export function AuthCard({ title, subtitle, children, footer }: AuthCardProps) {
  return (
    <div className="h-dvh overflow-y-auto bg-bg">
      <div className="flex min-h-full items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex flex-col items-center text-center">
            <div
              className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-cyan-500 text-lg font-bold text-white shadow-glow"
              aria-hidden
            >
              MM
            </div>
            <h1 className="font-display text-3xl tracking-wide text-fg">{title}</h1>
            {subtitle ? <p className="mt-2 text-sm text-muted">{subtitle}</p> : null}
          </div>

          <div className="glass-panel rounded-2xl border border-border/50 p-6 shadow-glass">
            {children}
          </div>

          {footer ? <div className="mt-6 text-center text-sm text-muted">{footer}</div> : null}
        </div>
      </div>
    </div>
  );
}
