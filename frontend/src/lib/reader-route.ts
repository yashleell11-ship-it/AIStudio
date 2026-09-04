/**
 * Whether a path is an immersive reader route — the source-native
 * `/reader/<sourceId>/<seriesKey>/<...chapterKey>`, but NOT the bare `/reader`
 * landing. The app shell uses this to drop the top bar, the mobile nav and the
 * profile chip, and to paint the obsidian reader background.
 */
export function isImmersiveReaderPath(pathname: string): boolean {
  return /^\/reader\/[^/]+\/.+/.test(pathname) || isReadAllPath(pathname);
}

/**
 * The Read-all run at `/read-all/<sourceId>/<seriesKey>` — the same immersive
 * manga reader with the whole series in one scroll, so the shell treats it
 * exactly as it treats a chapter.
 */
export function isReadAllPath(pathname: string): boolean {
  return /^\/read-all\/[^/]+\/[^/]+/.test(pathname);
}

/**
 * The same, for the novel reader at
 * `/novels/<sourceId>/<seriesKey>/<...chapterKey>`.
 *
 * A separate route (and so a separate test) rather than a `?kind=` on
 * `/reader/…`, because the two readers share no rendering: one is a virtualized
 * image strip on obsidian, the other is a text column painted in the reader's
 * chosen palette. The shell needs to tell them apart for exactly that reason —
 * both lose the app chrome, but only the manga reader gets the obsidian
 * background, since a Paper palette under a near-black page would defeat the
 * point of choosing Paper.
 */
export function isImmersiveNovelPath(pathname: string): boolean {
  return /^\/novels\/[^/]+\/.+/.test(pathname);
}

/** Either reader: the shell hides its chrome for both. */
export function isImmersivePath(pathname: string): boolean {
  return isImmersiveReaderPath(pathname) || isImmersiveNovelPath(pathname);
}
