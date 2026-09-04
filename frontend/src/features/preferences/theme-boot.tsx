import { THEME_BOOT_SCRIPT } from "./theme-boot-source";

/**
 * Emits the first-paint theme script into `<head>`.
 *
 * Rendered once, by the root layout, ahead of everything else. See
 * `theme-boot-source.ts` for what the script does and why it has to run before
 * React exists.
 *
 * `dangerouslySetInnerHTML` is the only way to emit an inline script from a
 * server component; the content is assembled from module constants and never
 * touches user input. It must NOT be a `next/script` — every strategy that
 * component offers runs after hydration, which is the exact moment this exists
 * to get ahead of.
 */
export function ThemeBootScript() {
  return <script id="mm-theme-boot" dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />;
}
