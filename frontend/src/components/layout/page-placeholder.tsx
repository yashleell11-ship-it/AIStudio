import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface PagePlaceholderProps {
  title: string;
  description: string;
  icon: LucideIcon;
  actionHref?: string;
  actionLabel?: string;
}

/**
 * Temporary scaffold for routes whose feature ships in a later phase.
 * Replaced by the real feature module when that phase lands.
 */
export function PagePlaceholder({
  title,
  description,
  icon: Icon,
  actionHref,
  actionLabel,
}: PagePlaceholderProps) {
  return (
    <div className="flex h-full min-h-[50vh] flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="flex size-14 items-center justify-center rounded-xl bg-surface-2 text-muted">
        <Icon className="size-7" aria-hidden />
      </div>
      <div className="flex flex-col items-center gap-2">
        <Badge variant="default">Coming soon</Badge>
        <h1 className="text-xl font-semibold text-fg">{title}</h1>
      </div>
      <p className="max-w-md text-sm text-muted">{description}</p>
      {actionHref && actionLabel ? (
        <Link
          href={actionHref}
          className="inline-flex h-10 items-center justify-center rounded-lg bg-surface-2 px-4 text-sm font-medium text-fg transition-colors hover:bg-border"
        >
          {actionLabel}
        </Link>
      ) : null}
    </div>
  );
}
