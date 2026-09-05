/**
 * When the library series page may point a chapter at a reader.
 *
 * A rule of its own, and tested like one, for the reason `read-all-link` is:
 * the vitest gate runs in node and cannot render a component, so a rule that
 * matters gets its own module.
 */

/**
 * Whether the reader links on the library series page may be drawn yet.
 *
 * Which reader a chapter opens in is the source's answer, made once in
 * `useChapterHref` (`features/novels/use-chapter-href`). Until the sources
 * listing resolves there is no answer there — only its fallback to the page
 * strip, which is the wrong reader for a novel. The library shelves novels
 * beside manga and the command palette links every library hit straight to
 * `/library/<id>`, so that fallback is reachable here, and prose in the page
 * strip is a reader that cannot render what it was handed.
 *
 * Waiting is the choice "Read all" already makes on this page
 * (`read-all-link`), and it is the same one the source series page makes for
 * the whole screen: a link that arrives a frame late costs nothing.
 */
export function chapterLinksReady(isNovel: boolean | undefined): boolean {
  return isNovel !== undefined;
}
