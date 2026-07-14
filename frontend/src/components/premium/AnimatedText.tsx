"use client";

import { useMemo, useRef } from "react";
import {
  motion,
  useScroll,
  useTransform,
  type MotionValue,
} from "framer-motion";

import { cn } from "@/lib/cn";
import { usePrefersReducedMotion } from "./use-prefers-reduced-motion";

export interface AnimatedTextProps {
  /** Text to animate. `text` and `children` are interchangeable. */
  text?: string;
  children?: string;
  className?: string;
}

interface CharProps {
  char: string;
  range: [number, number];
  progress: MotionValue<number>;
}

function Char({ char, range, progress }: CharProps) {
  const opacity = useTransform(progress, range, [0.2, 1]);
  return <motion.span style={{ opacity }}>{char}</motion.span>;
}

/**
 * Reveals text character-by-character as the paragraph scrolls through the
 * viewport, each glyph easing from 0.2 to full opacity. Honors reduced motion
 * by rendering plain, fully-opaque text.
 */
export function AnimatedText({ text, children, className }: AnimatedTextProps) {
  const reducedMotion = usePrefersReducedMotion();
  const value = text ?? children ?? "";
  const ref = useRef<HTMLParagraphElement>(null);

  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 0.8", "end 0.2"],
  });

  // Split into words so wrapping stays natural; each glyph gets a global index
  // (spaces included) so opacity ramps evenly across the whole string.
  const words = useMemo(() => {
    const total = value.length;
    const parts = value.split(" ");
    // Starting glyph index of each word: sum of prior word lengths + 1 space each.
    const starts = parts.map((_, i) =>
      parts.slice(0, i).reduce((sum, word) => sum + word.length + 1, 0),
    );
    return parts.map((word, wordIndex) =>
      word.split("").map((char, charIndex) => {
        const index = starts[wordIndex] + charIndex;
        return {
          char,
          range: [index / total, (index + 1) / total] as [number, number],
        };
      }),
    );
  }, [value]);

  if (reducedMotion) {
    return <p className={cn(className)}>{value}</p>;
  }

  return (
    <p ref={ref} className={cn("flex flex-wrap", className)}>
      {words.map((chars, wordIndex) => (
        <span
          key={wordIndex}
          className="mr-[0.25em] inline-flex whitespace-nowrap"
        >
          {chars.map(({ char, range }, charIndex) => (
            <Char
              key={charIndex}
              char={char}
              range={range}
              progress={scrollYProgress}
            />
          ))}
        </span>
      ))}
    </p>
  );
}

export default AnimatedText;
