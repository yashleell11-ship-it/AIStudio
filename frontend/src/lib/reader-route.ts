/**
 * Whether a path is an immersive reader route — the source-native
 * `/reader/<sourceId>/<seriesKey>/<...chapterKey>`, but NOT the bare `/reader`
 * landing. The app shell uses this to drop the top bar, the mobile nav and the
 * profile chip, and to paint the obsidian reader background.
 */
export function isImmersiveReaderPath(pathname: string): boolean {
  return /^\/reader\/[^/]+\/.+/.test(pathname);
}
