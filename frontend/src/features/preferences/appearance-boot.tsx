import { APPEARANCE_BOOT_SCRIPT } from "./appearance-boot-source";

/**
 * Emits the first-paint appearance script into `<head>`.
 *
 * Rendered once, by the root layout, ahead of everything else. It stamps both
 * `data-theme` (the palette) and `data-preset` (the design preset). See
 * `appearance-boot-source.ts` for what the script does and why it has to run
 * before React exists.
 *
 * `dangerouslySetInnerHTML` is the only way to emit an inline script from a
 * server component; the content is assembled from module constants and never
 * touches user input. It must NOT be a `next/script` — every strategy that
 * component offers runs after hydration, which is the exact moment this exists
 * to get ahead of.
 */
export function AppearanceBootScript() {
  return (
    <script id="mm-appearance-boot" dangerouslySetInnerHTML={{ __html: APPEARANCE_BOOT_SCRIPT }} />
  );
}
