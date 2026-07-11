import { Loader2 } from "lucide-react";

/**
 * Full-screen loading state shown while the session is being resolved or a
 * redirect is in flight. Deliberately minimal so it reads as "checking", not
 * as content.
 */
export function AuthPending() {
  return (
    <div className="flex h-dvh w-full items-center justify-center bg-bg">
      <Loader2 className="size-6 animate-spin text-muted" aria-label="Loading" />
    </div>
  );
}
