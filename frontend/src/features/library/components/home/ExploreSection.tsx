"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { ContrastSection } from "@/components/premium/ContrastSection";
import { FadeIn } from "@/components/premium/FadeIn";

interface ExploreItem {
  n: string;
  name: string;
  desc: string;
  href: string;
}

const ITEMS: ExploreItem[] = [
  {
    n: "01",
    name: "Library",
    desc: "Everything you follow, organized and always in sync.",
    href: "/library",
  },
  {
    n: "02",
    name: "Sources",
    desc: "Browse and add series from every connected source.",
    href: "/sources",
  },
  {
    n: "03",
    name: "Downloads",
    desc: "Save chapters for offline reading, anywhere.",
    href: "/downloads",
  },
  {
    n: "04",
    name: "Search",
    desc: "Find your next read across your whole collection.",
    href: "/search",
  },
  {
    n: "05",
    name: "Updates",
    desc: "Catch every new chapter the moment it drops.",
    href: "/updates",
  },
];

/**
 * Light "Explore" contrast section: an oversized dark heading over five indexed
 * rows that route into the app's core surfaces.
 */
export function ExploreSection() {
  return (
    <ContrastSection>
      <div className="mx-auto max-w-5xl">
        <h2 className="font-display text-[clamp(2.5rem,8vw,6rem)] font-black uppercase leading-none tracking-tight text-text-dark">
          Explore
        </h2>
        <div className="mt-10 border-t border-[rgba(12,12,12,0.12)] md:mt-14">
          {ITEMS.map((item, i) => (
            <FadeIn key={item.n} delay={i * 0.1}>
              <Link
                href={item.href}
                className="group flex items-center gap-5 border-b border-[rgba(12,12,12,0.12)] py-7 md:gap-8 md:py-9"
              >
                <span className="font-display text-4xl font-black tabular-nums text-text-dark/30 md:text-6xl">
                  {item.n}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-display text-2xl font-bold text-text-dark md:text-4xl">
                    {item.name}
                  </p>
                  <p className="mt-1 text-sm text-text-dark/60 md:text-base">
                    {item.desc}
                  </p>
                </div>
                <ChevronRight
                  className="size-6 shrink-0 text-text-dark/40 transition-transform duration-200 group-hover:translate-x-1"
                  aria-hidden
                />
              </Link>
            </FadeIn>
          ))}
        </div>
      </div>
    </ContrastSection>
  );
}
