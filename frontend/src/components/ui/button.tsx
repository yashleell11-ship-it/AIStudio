import { forwardRef } from "react";
import { cn } from "@/lib/cn";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg" | "icon";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium " +
  "transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-primary/60 disabled:pointer-events-none disabled:opacity-50 " +
  "active:scale-[0.98]";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-primary text-primary-fg hover:bg-primary-hover hover:shadow-glow",
  secondary:
    "border border-border/50 bg-white/[0.04] text-fg hover:border-primary/30 hover:bg-primary/10",
  ghost: "text-muted hover:bg-white/5 hover:text-fg",
  danger: "bg-danger text-white hover:opacity-90",
};

/**
 * `[@media(pointer:coarse)]` on `sm` and `icon`: 32px and 36px are comfortable
 * with a mouse and a mis-tap generator with a thumb. The bump applies only where
 * the primary input has no fine pointer — a phone or a tablet — so the desktop
 * app is byte-identical to what it was. 40px rather than the full 44 because
 * these two sizes exist precisely to sit in dense rows and toolbars, and pushing
 * them to 44 reflows those; the reading-path controls that had room (the bottom
 * tab bar, the novel reader's running head) do go the whole way.
 */
const sizes: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm [@media(pointer:coarse)]:h-10",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-6 text-base",
  icon: "h-9 w-9 [@media(pointer:coarse)]:size-10",
};

/** The single button primitive. Compose, don't fork — add variants here. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(base, variants[variant], sizes[size], className)}
      {...props}
    />
  ),
);

Button.displayName = "Button";
