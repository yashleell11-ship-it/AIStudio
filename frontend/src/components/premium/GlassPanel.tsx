import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface GlassPanelProps {
  className?: string;
  children: ReactNode;
}

/** Warm dark glass surface: blurred tint, subtle border, large radius. */
export function GlassPanel({ className, children }: GlassPanelProps) {
  return (
    <div className={cn("glass-panel rounded-3xl border border-border", className)}>
      {children}
    </div>
  );
}
