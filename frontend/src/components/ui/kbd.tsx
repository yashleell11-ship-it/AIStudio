import { cn } from "@/lib/cn";

interface KbdProps extends React.HTMLAttributes<HTMLElement> {
  children: React.ReactNode;
}

export function Kbd({ className, children, ...props }: KbdProps) {
  return (
    <kbd
      className={cn(
        "inline-flex min-w-[1.5rem] items-center justify-center rounded-md border border-border/60",
        "bg-white/[0.06] px-1.5 py-0.5 font-mono text-[11px] font-medium text-fg",
        "shadow-[inset_0_-1px_0_rgba(255,255,255,0.05)]",
        className,
      )}
      {...props}
    >
      {children}
    </kbd>
  );
}

interface KbdComboProps {
  tokens: string[];
  className?: string;
}

export function KbdCombo({ tokens, className }: KbdComboProps) {
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      {tokens.map((token, index) => (
        <Kbd key={`${token}-${index}`}>{token}</Kbd>
      ))}
    </span>
  );
}
