"use client";

import Image, { type ImageProps } from "next/image";
import { useState, type SyntheticEvent } from "react";

import { cn } from "@/lib/cn";

/**
 * A cover that arrives rather than appears.
 *
 * Every browsing surface in this app is a grid of covers, and each one used to
 * snap to full opacity the instant its bytes decoded. On a fast connection that
 * reads as a flicker; on a slow one it is forty covers popping in at forty
 * different moments, which is the single loudest reason the app felt abrupt
 * rather than smooth. Fading each one in over a fifth of a second turns that
 * into the grid filling itself.
 *
 * The fade lives in CSS (`[data-cover]` in `globals.css`) rather than here, for
 * two reasons: it scales with `--shape-motion` like every other duration in the
 * app, and the global `prefers-reduced-motion` block collapses it to nothing
 * without this component having to know that.
 *
 * Failure is treated as arrival. An `onError` that left the element at zero
 * opacity would hide the broken-image affordance and the alt text with it, so
 * the cover is revealed either way and a missing image looks missing.
 */
export function CoverImage({
  // Named rather than spread so the a11y lint can see it, and so the fact that
  // a cover fading in from nothing MUST carry alt text is visible here: at zero
  // opacity the alt text is hidden too, which is why `onError` reveals.
  alt,
  className,
  onLoad,
  onError,
  ...props
}: ImageProps) {
  const [settled, setSettled] = useState(false);

  // `next/image` fires `onLoad` for an image that was already complete when it
  // mounted (it checks `img.complete` itself), so a cover served from cache
  // does not need a ref to catch the load React missed.
  const reveal = (
    handler?: (event: SyntheticEvent<HTMLImageElement>) => void,
  ) => (event: SyntheticEvent<HTMLImageElement>) => {
    setSettled(true);
    handler?.(event);
  };

  return (
    <Image
      {...props}
      alt={alt}
      data-cover=""
      data-cover-settled={settled ? "true" : "false"}
      onLoad={reveal(onLoad)}
      onError={reveal(onError)}
      className={cn(className)}
    />
  );
}

export default CoverImage;
