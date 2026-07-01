import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

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
    <div className="page-shell flex min-h-[50vh] flex-col items-center justify-center text-center">
      <div className="empty-state max-w-lg">
        <div className="mx-auto mb-4 flex size-16 items-center justify-center rounded-full bg-violet-500/10">
          <Icon className="size-8 text-violet-400" aria-hidden />
        </div>
        <Badge variant="primary" className="mb-3">
          Coming soon
        </Badge>
        <h1 className="page-title">{title}</h1>
        <p className="page-subtitle mx-auto mt-3 max-w-md">{description}</p>
        {actionHref && actionLabel ? (
          <Link href={actionHref} className="mt-6 inline-block">
            <Button variant="secondary">{actionLabel}</Button>
          </Link>
        ) : null}
      </div>
    </div>
  );
}
