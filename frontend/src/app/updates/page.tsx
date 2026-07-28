// Imported from its own module rather than through the `@/features/updates`
// barrel. This page is a Server Component, and the barrel re-exports `./hooks`,
// which reaches `@/features/sources/source-progress` — a module that calls
// `useSyncExternalStore` and is not marked `"use client"`. Going through the
// barrel pulled that into the server graph and made this route fail to compile
// (a hard 500 on /updates). `UpdatesView` carries its own `"use client"`, so
// importing it directly keeps the whole chain inside the client boundary.
import { UpdatesView } from "@/features/updates/components/UpdatesView";

export default function UpdatesPage() {
  return <UpdatesView />;
}
