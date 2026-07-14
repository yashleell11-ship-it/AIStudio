import Image from "next/image";
import { cn } from "@/lib/cn";
import { sourceFaviconUrl } from "../source-branding";

interface SourceLogoProps {
  id: string;
  name: string;
  iconUrl?: string | null;
  size?: number;
  className?: string;
}

/** Connector mark — API favicon when available, else a letter tile. */
export function SourceLogo({
  id,
  name,
  iconUrl,
  size = 56,
  className,
}: SourceLogoProps) {
  const url = iconUrl ?? sourceFaviconUrl(id);
  const initial = name.trim().charAt(0).toUpperCase() || "?";

  return (
    <div
      className={cn(
        "relative shrink-0 overflow-hidden rounded-2xl border border-border bg-surface-2 ring-0 ring-primary/0 transition duration-200",
        "group-hover:ring-2 group-hover:ring-primary/40 group-focus-visible:ring-2 group-focus-visible:ring-primary",
        className,
      )}
      style={{ width: size, height: size }}
    >
      {url ? (
        <Image
          src={url}
          alt=""
          fill
          className="object-contain p-2"
          sizes={`${size}px`}
          unoptimized
        />
      ) : (
        <span
          aria-hidden
          className="flex h-full w-full items-center justify-center bg-gradient-to-br from-surface-2 to-surface text-lg font-semibold text-primary"
        >
          {initial}
        </span>
      )}
    </div>
  );
}
