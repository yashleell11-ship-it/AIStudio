"use client";

import Link from "next/link";
import { FadeIn } from "@/components/premium/FadeIn";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { Magnet } from "@/components/premium/Magnet";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { coverUrl } from "@/features/library/api";
import type { ContinueReadingItem } from "@/features/library/types";
import { HomeTopNav } from "./HomeTopNav";

export interface HeroSectionProps {
  /** Latest in-progress read, if any — drives the hero cover and CTA. */
  firstContinue?: ContinueReadingItem;
  /** Reader route for `firstContinue`, or `null` when nothing is in progress. */
  continueHref: string | null;
}

/**
 * Cinematic full-height hero: home nav, a massive two-line gradient wordmark, a
 * magnet-tracked continue-reading cover rising behind the text, and a tagline +
 * primary CTA anchored to the bottom.
 *
 * Sizing is container-relative: the section is a `@container`, so the heading
 * scales with `cqw` (the content column beside the fixed sidebar) rather than
 * raw `vw`. That is what keeps the wordmark inside the content area at every
 * breakpoint — notably a 1280px laptop with the sidebar expanded — instead of
 * clipping off the right edge.
 */
export function HeroSection({ firstContinue, continueHref }: HeroSectionProps) {
  const cover = firstContinue ? (
    // Covers are cookie-authed on web, so a raw <img> resolves fine.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={coverUrl(firstContinue.series_id)}
      alt={firstContinue.series_title}
      className="aspect-[2/3] w-full rounded-3xl object-cover shadow-glow ring-1 ring-border"
    />
  ) : (
    // Premium empty state: a warm gradient-framed placeholder with a faint amber
    // glow, kept self-contained inside the card so nothing collides with the
    // heading above it.
    <div className="relative flex aspect-[2/3] w-full items-center justify-center overflow-hidden rounded-3xl bg-gradient-to-br from-surface-2 via-surface to-bg shadow-glow ring-1 ring-primary/30">
      <div
        aria-hidden
        className="absolute inset-0 bg-[radial-gradient(circle_at_50%_32%,rgba(245,158,11,0.18),transparent_70%)]"
      />
      <div className="relative flex flex-col items-center gap-3 text-center">
        <span className="font-display text-4xl font-black text-primary/70">
          MM
        </span>
        <span className="text-[0.62rem] uppercase tracking-[0.3em] text-muted">
          Nothing in progress
        </span>
      </div>
    </div>
  );

  return (
    <section className="@container relative flex min-h-screen flex-col overflow-x-clip px-6 pb-10 pt-8 md:px-10 md:pb-14">
      <HomeTopNav />

      <div className="relative flex flex-1 items-center justify-center">
        {/* Cover sits BEHIND the wordmark (z-0). Coherent centered position at
            every breakpoint — the Magnet only nudges it toward the cursor. */}
        <Magnet className="pointer-events-none absolute left-1/2 top-1/2 z-0 w-[220px] -translate-x-1/2 -translate-y-1/2 sm:w-[280px] md:w-[340px] lg:w-[420px]">
          {continueHref ? (
            <Link
              href={continueHref}
              className="pointer-events-auto block"
              aria-label={
                firstContinue
                  ? `Continue reading ${firstContinue.series_title}`
                  : "Continue reading"
              }
            >
              {cover}
            </Link>
          ) : (
            cover
          )}
        </Magnet>

        {/* Radial scrim between the cover and the text so the wordmark stays
            legible over the portrait without muddying it. */}
        <div
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-1/2 z-[5] h-[70cqw] w-[95cqw] -translate-x-1/2 -translate-y-1/2 bg-[radial-gradient(ellipse_at_center,rgba(10,10,10,0.72)_35%,transparent_72%)]"
        />

        <FadeIn className="relative z-10 text-center" delay={0.05}>
          <HeroHeading className="text-[clamp(2.75rem,19cqw,10rem)] leading-[0.82]">
            <span className="block">Your</span>
            <span className="block">Library</span>
          </HeroHeading>
        </FadeIn>
      </div>

      <div className="relative z-10 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <p className="max-w-xs text-[clamp(0.7rem,2vw,0.95rem)] uppercase tracking-widest text-muted">
          A premium manga &amp; webtoon experience built for readers who want
          more
        </p>
        {continueHref ? (
          <PrimaryPillButton label="Continue Reading" href={continueHref} />
        ) : (
          <PrimaryPillButton label="Browse Library" href="/library" />
        )}
      </div>
    </section>
  );
}
