import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface HeroHeadingProps {
  children: ReactNode;
  className?: string;
  /** Heading level. Defaults to `h1`. */
  as?: "h1" | "h2";
}

/**
 * Bronze→cream gradient hero heading (Syne display face). The default size is a
 * responsive clamp; pass `className` to override sizing or tracking.
 */
export function HeroHeading({ children, className, as = "h1" }: HeroHeadingProps) {
  const Tag = as;
  return (
    <Tag
      className={cn(
        // The lower bound is 1.75rem, not 2.5rem: at 2.5rem an eight-letter
        // word ("SETTINGS") in this weight is wider than a 390px phone, and the
        // last letter was being clipped off the right edge. Above ~500px the
        // 8vw term wins and nothing changes.
        "hero-heading font-display text-[clamp(1.75rem,8vw,6rem)] font-black uppercase leading-none tracking-tight",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
