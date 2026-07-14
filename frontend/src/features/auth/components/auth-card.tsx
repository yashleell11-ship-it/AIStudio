import type { ReactNode } from "react";
import { FadeIn } from "@/components/premium/FadeIn";
import { GlassPanel } from "@/components/premium/GlassPanel";
import { HeroHeading } from "@/components/premium/HeroHeading";

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
        <FadeIn className="w-full max-w-md" y={20}>
          <div className="mb-8 flex flex-col items-center text-center">
            <div
              className="mb-5 flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-accent text-lg font-bold text-white shadow-glow"
              aria-hidden
            >
              MM
            </div>
            <HeroHeading className="text-4xl sm:text-[2.75rem]">{title}</HeroHeading>
            {subtitle ? <p className="mt-3 text-sm text-muted">{subtitle}</p> : null}
          </div>

          <GlassPanel className="p-6 shadow-glass">{children}</GlassPanel>

          {footer ? <div className="mt-6 text-center text-sm text-muted">{footer}</div> : null}
        </FadeIn>
      </div>
    </div>
  );
}
