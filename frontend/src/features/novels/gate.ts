import type { BootstrapStatus } from "@/features/auth/types";
import type { SourceSummary } from "@/features/sources/types";

/**
 * Whether any novel UI may exist right now (spec §2, "build it but don't ship
 * it").
 *
 * `novels_enabled` rides on `GET /auth/bootstrap-status` — the pre-auth config
 * read the clients already make — so the web build ships the novel code dormant
 * and one env var on the VPS turns it on. Every novel surface mounts behind
 * this: with the flag off the app must look **exactly** as it does today, not
 * "the same but with a disabled tab".
 *
 * Absent on an older backend, which is the same thing as off: a deployment that
 * has never heard of the flag has no novel connectors to browse either.
 *
 * There is a second, independent gate underneath this one, and it is the reason
 * the branch is safe even before the status has loaded: `content_kind` only
 * ever says `"novel"` for a source the server chose to list, and with the flag
 * off the registry hides novel connectors from `/sources/*` entirely. So a
 * dark deployment has no novel sources, no novel series pages, and nothing that
 * links to a novel reader.
 */
export function isNovelsEnabled(status: BootstrapStatus | null | undefined): boolean {
  return status?.novels_enabled === true;
}

/** Whether a source serves prose rather than pages. */
export function isNovelSource(source: SourceSummary | null | undefined): boolean {
  return source?.content_kind === "novel";
}

/*
 * There is deliberately no `readerKindForSource` here.
 *
 * "Which reader does this open in?" is only ever asked in order to build a
 * link, and `useChapterHref` (`use-chapter-href.ts`) is where that decision is
 * made — once, for every screen that links into a chapter. A second helper
 * answering the same question is a second place for the two answers to
 * disagree.
 */
