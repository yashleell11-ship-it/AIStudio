"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import { usePrefersReducedMotion } from "./use-prefers-reduced-motion";

export interface MagnetProps {
  children: ReactNode;
  /** Activation radius in px around the element bounds (default 150). */
  padding?: number;
  /** Higher = weaker pull; cursor delta is divided by this (default 3). */
  strength?: number;
  disabled?: boolean;
  className?: string;
}

/**
 * Mouse-follow wrapper: while the cursor is within `padding` of the element,
 * the content translates toward it. Resets on leave. Disabled under reduced
 * motion or via `disabled`.
 */
export function Magnet({
  children,
  padding = 150,
  strength = 3,
  disabled = false,
  className,
}: MagnetProps) {
  const reducedMotion = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(false);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  const inert = disabled || reducedMotion;

  useEffect(() => {
    // When inert we skip the listener; the render below ignores stale state and
    // draws no transform, so there is no need to reset state here.
    if (inert) return;

    const handleMove = (event: MouseEvent) => {
      const el = ref.current;
      if (!el) return;

      const { left, top, width, height } = el.getBoundingClientRect();
      const centerX = left + width / 2;
      const centerY = top + height / 2;
      const distX = event.clientX - centerX;
      const distY = event.clientY - centerY;

      const withinX = Math.abs(distX) < width / 2 + padding;
      const withinY = Math.abs(distY) < height / 2 + padding;

      if (withinX && withinY) {
        setActive(true);
        setOffset({ x: distX / strength, y: distY / strength });
      } else {
        setActive(false);
        setOffset({ x: 0, y: 0 });
      }
    };

    window.addEventListener("mousemove", handleMove, { passive: true });
    return () => window.removeEventListener("mousemove", handleMove);
  }, [inert, padding, strength]);

  return (
    <div
      ref={ref}
      className={cn(className)}
      style={{
        transform: inert
          ? "none"
          : `translate3d(${offset.x}px, ${offset.y}px, 0)`,
        transition:
          active && !inert
            ? "transform 0.3s ease-out"
            : "transform 0.6s ease-in-out",
        willChange: "transform",
      }}
    >
      {children}
    </div>
  );
}

export default Magnet;
