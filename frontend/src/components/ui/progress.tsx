import { cn } from "@/lib/cn";

interface ProgressProps {
  value: number;
  className?: string;
  variant?: "default" | "gradient";
  "aria-label"?: string;
}

export function Progress({
  value,
  className,
  variant = "default",
  "aria-label": ariaLabel,
}: ProgressProps) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div
      className={cn("h-2 w-full overflow-hidden rounded-full bg-white/5", className)}
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clamped}
    >
      <div
        className={cn(
          "h-full rounded-full transition-all duration-500 ease-out",
          variant === "gradient"
            ? "bg-gradient-to-r from-accent to-primary"
            : "bg-primary",
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
