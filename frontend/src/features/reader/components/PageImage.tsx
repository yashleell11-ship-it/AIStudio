"use client";

import Image from "next/image";
import { memo, useEffect, useState } from "react";
import { readerDebug } from "../debug";
import { pageContainerStyle } from "../page-layout";

interface PageImageProps {
  imageUrl: string;
  alt: string;
  width?: number | null;
  height?: number | null;
  priority?: boolean;
  onLoad?: () => void;
}

export const PageImage = memo(function PageImage({
  imageUrl,
  alt,
  width,
  height,
  priority,
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
      className="relative w-full overflow-hidden rounded-sm bg-black shadow-lg shadow-black/40"
      style={pageContainerStyle(loaded, width, height)}
    >
      <Image
        src={imageUrl}
        alt={alt}
        width={imageWidth}
        height={imageHeight}
        className="block h-auto w-full object-contain"
        style={{ width: "100%", height: "auto", display: "block" }}
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
