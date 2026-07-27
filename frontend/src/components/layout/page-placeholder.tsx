import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

interface PagePlaceholderProps {
  title: string;
  description: string;
  icon: LucideIcon;
  actionHref?: string;
  actionLabel?: string;
}

/**
 * Empty state for a route that needs a selection before it can render anything —
 * /reader without a series, for example. Not a "not built yet" placeholder: the
 * features behind these routes exist, so it points at where to make the choice.
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
        <div className="mx-auto mb-4 flex size-16 items-center justify-center rounded-full bg-primary/10">
          <Icon className="size-8 text-primary" aria-hidden />
        </div>
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
