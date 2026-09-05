"use client";

import Image from "next/image";
import { memo, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { readerDebug } from "../debug";
import { pageContainerStyle, UNKNOWN_PAGE_ASPECT } from "../page-layout";

export interface PageFrame {
  width: number;
  height: number;
}

/** Only ever a denominator: `next/image` wants a number, the layout wants a ratio. */
const DEFAULT_INTRINSIC_WIDTH = 800;

interface PageImageProps {
  imageUrl: string;
  alt: string;
  width?: number | null;
  height?: number | null;
  priority?: boolean;
  seamless?: boolean;
  /**
   * Exact rendered box, in CSS pixels. The paged modes resolve their own layout
   * (fit width / height / original + zoom) and need the space reserved before
   * the image decodes so a page turn never reflows under the reader. Continuous
   * scrolling leaves this unset and stays fluid.
   */
  frame?: PageFrame | null;
  /**
   * Fired once the image has decoded, carrying its INTRINSIC size — `null` when
   * the browser resolved none. That size is the only trustworthy shape a page
   * has when its connector reports no dimensions: the row's own box is still
   * the placeholder at this point in the commit, so a caller that measured the
   * DOM here would sample the guess it is trying to replace.
   */
  onLoad?: (natural: PageFrame | null) => void;
}

export const PageImage = memo(function PageImage({
  imageUrl,
  alt,
  width,
  height,
  priority,
  seamless = true,
  frame = null,
  onLoad,
}: PageImageProps) {
  const [loaded, setLoaded] = useState(false);
  // `next/image` requires an intrinsic size, and with an unknown page the only
  // honest one is the same prior the container's placeholder box uses — a
  // second guess here would make the image and its box disagree before decode.
  const imageWidth = width && width > 0 ? width : DEFAULT_INTRINSIC_WIDTH;
  const imageHeight =
    height && height > 0 ? height : Math.round(DEFAULT_INTRINSIC_WIDTH * UNKNOWN_PAGE_ASPECT);

  useEffect(() => {
    setLoaded(false);
  }, [imageUrl]);

  useEffect(() => {
    readerDebug("page-image-mounted", { alt, imageUrl });
  }, [alt, imageUrl]);

  return (
    <div
      className={cn(
        // Letterboxing / placeholder fill uses the reader backdrop so any
        // aspect mismatch blends into the page flow instead of a harsh black seam.
        "relative overflow-hidden bg-bg",
        frame ? "shrink-0" : "w-full",
        seamless ? "block" : "rounded-sm shadow-lg shadow-black/40",
      )}
      style={
        frame
          ? { width: `${frame.width}px`, height: `${frame.height}px` }
          : pageContainerStyle(loaded, width, height)
      }
    >
      <Image
        src={imageUrl}
        alt={alt}
        width={imageWidth}
        height={imageHeight}
        className={cn("block object-contain", frame ? "h-full w-full" : "h-auto w-full")}
        style={
          frame
            ? { width: "100%", height: "100%", display: "block" }
            : { width: "100%", height: "auto", display: "block" }
        }
        priority={priority}
        loading={priority ? undefined : "lazy"}
        unoptimized
        onLoad={(event) => {
          setLoaded(true);
          const img = event.currentTarget;
          onLoad?.(
            img.naturalWidth > 0 && img.naturalHeight > 0
              ? { width: img.naturalWidth, height: img.naturalHeight }
              : null,
          );
        }}
      />
    </div>
  );
});
