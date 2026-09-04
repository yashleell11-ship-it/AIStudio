/**
 * One stable `ref` callback per paragraph, for the lifetime of a chapter.
 *
 * React compares a ref callback by identity. A fresh arrow per paragraph per
 * render therefore makes React detach and reattach EVERY paragraph on EVERY
 * render — `ref(null)` then `ref(node)` — and a chapter of prose runs to
 * hundreds of paragraphs. Handing back the same function for the same index
 * makes a re-render of the column cost nothing at all.
 *
 * This is not only a speed question. `measureOffsets` walks `paragraphNodes`
 * to build the offsets a bookmark's paragraph index is captured and resolved
 * against (`paragraph-anchor.ts`), so a ref that wrote a node under the wrong
 * index — or stopped writing one at all — would move saved reading positions
 * rather than merely cost a frame. That is what earns this a module with a
 * test of its own instead of an arrow in the paragraph map.
 *
 * Pure, so the identity guarantee is testable without a DOM — the same
 * division of labour as `progress.ts` next to it.
 */

/** What React is handed for a single paragraph. */
export type ParagraphRef = (node: HTMLParagraphElement | null) => void;

/** The ref callback for a paragraph, identical on every call for that index. */
export type ParagraphRefs = (index: number) => ParagraphRef;

export function createParagraphRefs(
  register: (index: number, node: HTMLParagraphElement | null) => void,
): ParagraphRefs {
  const refs = new Map<number, ParagraphRef>();
  return (index) => {
    const existing = refs.get(index);
    if (existing) return existing;
    const ref: ParagraphRef = (node) => {
      register(index, node);
    };
    refs.set(index, ref);
    return ref;
  };
}
