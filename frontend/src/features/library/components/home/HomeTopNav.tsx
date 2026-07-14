"use client";

import Link from "next/link";
import { FadeIn } from "@/components/premium/FadeIn";

const linkClass =
  "text-fg transition-opacity duration-200 hover:opacity-70 focus-visible:opacity-70 focus-visible:outline-none";

/**
 * Home-only top navigation. "About" scrolls to the in-page About section; the
 * rest route to real destinations. Uppercase, tracked, sized up on wider
 * viewports per the Eclipse Warm hero contract.
 */
export function HomeTopNav() {
  const scrollToAbout = () => {
    document
      .getElementById("home-about")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <FadeIn as="nav" className="relative z-20">
      <ul className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm font-medium uppercase tracking-widest md:gap-x-10 md:text-lg lg:text-[1.4rem]">
        <li>
          <button type="button" onClick={scrollToAbout} className={linkClass}>
            About
          </button>
        </li>
        <li>
          <Link href="/library" className={linkClass}>
            Library
          </Link>
        </li>
        <li>
          <Link href="/sources" className={linkClass}>
            Sources
          </Link>
        </li>
        <li>
          <Link href="/settings" className={linkClass}>
            Contact
          </Link>
        </li>
      </ul>
    </FadeIn>
  );
}
