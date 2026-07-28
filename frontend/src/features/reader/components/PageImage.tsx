"use client";

import Image from "next/image";
import { memo, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { readerDebug } from "../debug";
import { pageContainerStyle } from "../page-layout";

export interface PageFrame {
  width: number;
  height: number;
}

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
  onLoad?: () => void;
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
  const imageWidth = width && width > 0 ? width : 800;
  const imageHeight = height && height > 0 ? height : 1200;

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
        onLoad={() => {
          setLoaded(true);
          onLoad?.();
        }}
      />
    </div>
  );
});
