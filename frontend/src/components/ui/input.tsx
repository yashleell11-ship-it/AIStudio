import { forwardRef } from "react";
import { cn } from "@/lib/cn";

type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-10 w-full rounded-lg border border-border/50 bg-white/[0.03] px-3 py-2 text-sm text-fg",
        "placeholder:text-muted transition-colors duration-200",
        "focus-visible:outline-none focus-visible:border-violet-500/40 focus-visible:ring-2 focus-visible:ring-primary/40",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = "Input";
