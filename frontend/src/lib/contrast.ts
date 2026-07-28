/**
 * WCAG 2.1 relative luminance and contrast ratios.
 *
 * Exists so "this text passes AA" is a thing the test suite can assert about the
 * palette rather than a thing someone checked once in a browser extension and
 * then a theme was added. Small and dependency-free on purpose.
 */

export interface Rgb {
  r: number;
  g: number;
  b: number;
  /** 0–1. Colours in the palette are opaque; overlays are not. */
  a: number;
}

/**
 * Parse `#rgb`, `#rrggbb`, `#rrggbbaa`, `rgb(...)` or `rgba(...)`.
 * Returns `null` for anything else — a caller that meant a colour and got a
 * gradient should hear about it rather than silently score `#000`.
 */
export function parseColor(value: string): Rgb | null {
  const input = value.trim();

  const hex = /^#([0-9a-f]{3,8})$/i.exec(input);
  if (hex) {
    const digits = hex[1];
    if (digits.length === 3 || digits.length === 4) {
      const [r, g, b, a] = digits.split("").map((d) => parseInt(d + d, 16));
      return { r, g, b, a: digits.length === 4 ? a / 255 : 1 };
    }
    if (digits.length === 6 || digits.length === 8) {
      const pair = (index: number) => parseInt(digits.slice(index * 2, index * 2 + 2), 16);
      return {
        r: pair(0),
        g: pair(1),
        b: pair(2),
        a: digits.length === 8 ? pair(3) / 255 : 1,
      };
    }
    return null;
  }

  const rgb = /^rgba?\(([^)]+)\)$/i.exec(input);
  if (rgb) {
    const parts = rgb[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    if (parts.length < 3 || parts.some(Number.isNaN)) return null;
    return { r: parts[0], g: parts[1], b: parts[2], a: parts[3] ?? 1 };
  }

  return null;
}

/** Flatten a translucent colour over an opaque backdrop. */
export function over(foreground: Rgb, background: Rgb): Rgb {
  const alpha = foreground.a;
  return {
    r: foreground.r * alpha + background.r * (1 - alpha),
    g: foreground.g * alpha + background.g * (1 - alpha),
    b: foreground.b * alpha + background.b * (1 - alpha),
    a: 1,
  };
}

function channelLuminance(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG relative luminance, 0 (black) to 1 (white). */
export function relativeLuminance({ r, g, b }: Rgb): number {
  return (
    0.2126 * channelLuminance(r) +
    0.7152 * channelLuminance(g) +
    0.0722 * channelLuminance(b)
  );
}

/**
 * Contrast ratio between two colours, 1–21. A translucent `foreground` is
 * flattened over `background` first, which is what the browser draws and
 * therefore what the reader actually sees — scoring the raw colour would pass
 * `text-muted/40` that is invisible on screen.
 */
export function contrastRatio(foreground: Rgb, background: Rgb): number {
  const front = foreground.a < 1 ? over(foreground, background) : foreground;
  const a = relativeLuminance(front);
  const b = relativeLuminance(background);
  const lighter = Math.max(a, b);
  const darker = Math.min(a, b);
  return (lighter + 0.05) / (darker + 0.05);
}

/** Convenience: contrast between two CSS colour strings. Throws on unparseable input. */
export function contrastBetween(foreground: string, background: string): number {
  const front = parseColor(foreground);
  const back = parseColor(background);
  if (front === null) throw new Error(`Unparseable colour: ${foreground}`);
  if (back === null) throw new Error(`Unparseable colour: ${background}`);
  return contrastRatio(front, back);
}

/** WCAG AA minimums. Large is >= 18.66px bold or >= 24px. */
export const WCAG_AA_NORMAL_TEXT = 4.5;
export const WCAG_AA_LARGE_TEXT = 3;
/** Icons, focus indicators, input borders — anything non-text that carries meaning. */
export const WCAG_AA_NON_TEXT = 3;
