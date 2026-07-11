"use client";

import { useEffect, useRef } from "react";

export function useLoadMoreOnScroll(
  enabled: boolean,
  onLoadMore: () => void,
  isLoading: boolean,
) {
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const element = sentinelRef.current;
    if (!element) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !isLoading) {
          onLoadMore();
        }
      },
      { rootMargin: "480px" },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [enabled, isLoading, onLoadMore]);

  return sentinelRef;
}
