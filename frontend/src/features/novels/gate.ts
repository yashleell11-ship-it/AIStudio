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
 * There is a second, independent gate underneath this one, and it is what makes
 * a DARK deployment safe however late this flag arrives: `content_kind` only
 * ever says `"novel"` for a source the server chose to list, and with the flag
 * off the registry hides novel connectors from `/sources/*` entirely. So a
 * dark deployment has no novel sources, no novel series pages, and nothing that
 * links to a novel reader.
 *
 * It says nothing about a deployment that HAS novels, which is where reading an
 * unanswered probe as `false` stops being harmless — see `resolveNovelsEnabled`.
 */
export function isNovelsEnabled(status: BootstrapStatus | null | undefined): boolean {
  return status?.novels_enabled === true;
}

/** Whether a source serves prose rather than pages. */
export function isNovelSource(source: SourceSummary | null | undefined): boolean {
  return source?.content_kind === "novel";
}

/**
 * The same flag as a THREE-state answer: on, off, or not answered yet.
 *
 * `isNovelsEnabled` collapses an unanswered probe into `false`, which is the
 * right answer for "may novel UI mount" and the wrong one for "which reader
 * does this chapter open in": a link built from that `false` sends prose to the
 * page strip, and on a novels-enabled deployment it is wrong for the whole cold
 * window rather than for no time at all.
 *
 * `pending` is the query's own `isPending` rather than `status === undefined`,
 * because the probe is `retry: false` — a backend that cannot be reached
 * settles with no data, and that is a resolved "off" (the older-backend case
 * above), not an answer still worth waiting for.
 */
export function resolveNovelsEnabled(
  status: BootstrapStatus | null | undefined,
  pending: boolean,
): boolean | undefined {
  return pending ? undefined : isNovelsEnabled(status);
}

/**
 * Whether "which medium does this source serve?" can be answered at all yet.
 *
 * Novels being OFF is itself a complete answer, and has to be: the sources
 * listing is not fetched on a manga-only deployment, so a rule that waited for
 * it there would wait for a request nobody will make. Only a deployment that
 * has novels needs the listing before it can say.
 */
export function sourceKindsKnown(
  novelsEnabled: boolean | undefined,
  sources: readonly SourceSummary[] | undefined,
): boolean {
  if (novelsEnabled === undefined) return false;
  return !novelsEnabled || sources !== undefined;
}

/**
 * Whether one source serves prose — `undefined` while that is genuinely
 * unknown, so a caller can hold the decision for a frame instead of being told
 * "manga" and linking prose into the page strip.
 *
 * A source the listing does not carry reads as pages rather than unknown. That
 * is an answer too, just one about a source this profile can no longer see: an
 * uninstalled connector still named by reading history or a bookmark.
 */
export function resolveNovelSource(
  novelsEnabled: boolean | undefined,
  sources: readonly SourceSummary[] | undefined,
  sourceId: string,
): boolean | undefined {
  if (!sourceKindsKnown(novelsEnabled, sources)) return undefined;
  if (!novelsEnabled || !sources) return false;
  return isNovelSource(sources.find((source) => source.id === sourceId));
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
