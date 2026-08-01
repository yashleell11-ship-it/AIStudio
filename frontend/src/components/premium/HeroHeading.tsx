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
        // Sized off MEASURED width, not guesswork. Syne in this weight renders
        // roughly 1.25em per uppercase character, so "Downloads" at the old
        // 8vw was 417px inside a 364px column on a 412px phone -- the last
        // letters were clipped clean off. 6.5vw keeps a ten-character heading
        // inside the gutter at every phone width.
        //
        // `break-words` is the backstop, because no single ratio can be right
        // for headings spanning "More" to "Recommendations": a word that still
        // will not fit wraps instead of running off the edge.
        "hero-heading font-display text-[clamp(1.5rem,6.5vw,6rem)] font-black uppercase leading-none tracking-tight break-words",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
