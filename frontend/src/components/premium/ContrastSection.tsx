import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface ContrastSectionProps {
  className?: string;
  children: ReactNode;
}

/**
 * White contrast section wrapper with a rounded top edge. Flips the palette to
 * dark text on a light surface; children/dividers are styled by the caller.
 */
export function ContrastSection({ className, children }: ContrastSectionProps) {
  return (
    <section
      className={cn(
        "rounded-t-[40px] bg-bg-light px-6 py-24 text-text-dark sm:rounded-t-[50px] md:rounded-t-[60px]",
        className,
      )}
    >
      {children}
    </section>
  );
}
