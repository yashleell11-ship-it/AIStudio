"use client";

import { AnimatedText } from "@/components/premium/AnimatedText";
import { FadeIn } from "@/components/premium/FadeIn";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";

const ABOUT_COPY =
  "ManhwaManiacs is a premium home for every series you love, bringing manga, manhwa, and webtoons together in one beautifully fast library. Track your progress, discover your next obsession, and pick up exactly where you left off.";

/**
 * Full-height About section — the "About" nav link scrolls here. A gradient
 * heading, scroll-revealed copy, and a CTA into the library.
 */
export function AboutSection() {
  return (
    <section
      id="home-about"
      className="flex min-h-screen flex-col items-center justify-center gap-10 bg-bg px-6 py-24 text-center md:px-10"
    >
      <FadeIn>
        <HeroHeading as="h2">About</HeroHeading>
      </FadeIn>
      <AnimatedText
        text={ABOUT_COPY}
        className="max-w-3xl justify-center text-2xl font-medium leading-snug text-fg md:text-3xl"
      />
      <FadeIn delay={0.1}>
        <PrimaryPillButton label="Browse Library" href="/library" />
      </FadeIn>
    </section>
  );
}
