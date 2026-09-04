import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { createParagraphRefs, type ParagraphRef } from "./paragraph-refs";

/** Stand-ins for the `<p>` elements; nothing here touches a real DOM. */
function fakeNodes(count: number): HTMLParagraphElement[] {
  return Array.from(
    { length: count },
    (_, index) => ({ index }) as unknown as HTMLParagraphElement,
  );
}

/**
 * What React does to a column of ref callbacks between two renders: a callback
 * whose identity changed is detached with `null` and its replacement is called
 * with the node; an identical callback is left alone entirely. Paragraphs the
 * next render no longer has are unmounted, which detaches them too.
 */
function commitRefs(
  previous: readonly ParagraphRef[],
  next: readonly ParagraphRef[],
  nodes: readonly HTMLParagraphElement[],
): void {
  for (let index = next.length; index < previous.length; index += 1) {
    previous[index](null);
  }
  next.forEach((ref, index) => {
    if (previous[index] === ref) return;
    previous[index]?.(null);
    ref(nodes[index]);
  });
}

describe("createParagraphRefs", () => {
  it("hands back the same callback for a paragraph every time", () => {
    const refs = createParagraphRefs(() => {});
    expect(refs(7)).toBe(refs(7));
  });

  it("gives each paragraph its own", () => {
    const refs = createParagraphRefs(() => {});
    expect(refs(7)).not.toBe(refs(8));
  });

  it("writes a node against the paragraph's own index", () => {
    const writes: Array<[number, HTMLParagraphElement | null]> = [];
    const refs = createParagraphRefs((index, node) => writes.push([index, node]));
    const nodes = fakeNodes(3);

    refs(2)(nodes[2]);
    refs(0)(nodes[0]);
    refs(2)(null);

    expect(writes).toEqual([
      [2, nodes[2]],
      [0, nodes[0]],
      [2, null],
    ]);
  });
});

/**
 * The regression this exists for.
 *
 * Scrolling a chapter used to re-render the whole column ~30 times a second,
 * and each render built a fresh arrow per paragraph — so React tore every
 * paragraph's ref down and put it back, hundreds of times a frame, while the
 * reader was reading. The second test measures that cost, so a revert shows
 * up as a number rather than as a reader saying the page feels slow.
 */
describe("a column that re-renders while scrolling", () => {
  const PARAGRAPHS = 500;
  const FRAMES = 30;

  it("attaches each paragraph once and never detaches it", () => {
    const writes: Array<[number, HTMLParagraphElement | null]> = [];
    const refs = createParagraphRefs((index, node) => writes.push([index, node]));
    const nodes = fakeNodes(PARAGRAPHS);

    let previous: ParagraphRef[] = [];
    for (let frame = 0; frame < FRAMES; frame += 1) {
      const rendered = nodes.map((_, index) => refs(index));
      commitRefs(previous, rendered, nodes);
      previous = rendered;
    }

    expect(writes).toHaveLength(PARAGRAPHS);
    expect(writes.some(([, node]) => node === null)).toBe(false);
  });

  it("is what stops the fresh-arrow cost, which is two calls per paragraph per frame", () => {
    const writes: Array<[number, HTMLParagraphElement | null]> = [];
    const register = (index: number, node: HTMLParagraphElement | null) =>
      writes.push([index, node]);
    const nodes = fakeNodes(PARAGRAPHS);

    let previous: ParagraphRef[] = [];
    for (let frame = 0; frame < FRAMES; frame += 1) {
      const rendered = nodes.map(
        (_, index): ParagraphRef =>
          (node) => {
            register(index, node);
          },
      );
      commitRefs(previous, rendered, nodes);
      previous = rendered;
    }

    expect(writes).toHaveLength(PARAGRAPHS + (FRAMES - 1) * PARAGRAPHS * 2);
  });
});

/**
 * The half of this that is not about frame rate.
 *
 * `measureOffsets` walks `paragraphNodes` in paragraph order and a bookmark
 * records an index into the offsets it builds (`paragraph-anchor.ts`). So the
 * registry has to leave that array holding every live paragraph under its own
 * index — through a scroll, and through a seamless chapter swap, which is the
 * one moment the column's length changes underneath it. Getting this wrong
 * would not look like jank; it would look like bookmarks quietly reopening a
 * paragraph or two off.
 */
describe("the array a bookmark is resolved against", () => {
  /** `NovelChapterView`'s `registerParagraph`, verbatim. */
  function paragraphNodes() {
    const nodes: (HTMLParagraphElement | null)[] = [];
    const refs = createParagraphRefs((index, node) => {
      nodes[index] = node;
    });
    let previous: ParagraphRef[] = [];
    return {
      nodes,
      render(rendered: readonly HTMLParagraphElement[]) {
        const next = rendered.map((_, index) => refs(index));
        commitRefs(previous, next, rendered);
        previous = next;
      },
    };
  }

  it("holds every node under its own index after a scroll's worth of renders", () => {
    const column = paragraphNodes();
    const nodes = fakeNodes(500);

    for (let frame = 0; frame < 30; frame += 1) column.render(nodes);

    expect(column.nodes).toEqual(nodes);
  });

  it("keeps the paragraphs that survive a seamless swap into a shorter chapter", () => {
    const column = paragraphNodes();
    const long = fakeNodes(6);
    const short = long.slice(0, 3);

    column.render(long);
    column.render(short);

    expect(column.nodes).toEqual([...short, null, null, null]);
  });

  it("refills the tail when the chapter after that is long again", () => {
    const column = paragraphNodes();
    const long = fakeNodes(6);

    column.render(long);
    column.render(long.slice(0, 3));
    column.render(long);

    expect(column.nodes).toEqual(long);
  });
});

/**
 * The guarantee only holds while the reader actually goes through the module:
 * an inline `ref={(node) => …}` back in the paragraph map would pass every
 * test above and reintroduce the bug. There is no DOM in this suite (see
 * `vitest.config.ts`), so the wiring is pinned at the source, the way
 * `typography.test.ts` pins `--font-book`.
 */
describe("NovelChapterView's wiring", () => {
  const SOURCE = readFileSync(
    path.resolve(__dirname, "./components/NovelChapterView.tsx"),
    "utf8",
  );
  const DECLARATION = "function ChapterBody(";
  /**
   * ChapterBody alone. Bounded at the next component rather than run to the
   * end of the file, so an unrelated callback in the skeleton below it cannot
   * fail the ref check on its behalf.
   */
  const PROSE = SOURCE.slice(
    SOURCE.indexOf(DECLARATION),
    SOURCE.indexOf("function ChapterSkeleton("),
  );

  it("still has a ChapterBody to check, so the rest of this is looking at it", () => {
    expect(SOURCE).toContain(DECLARATION);
    expect(SOURCE).toContain("function ChapterSkeleton(");
    expect(PROSE).toContain("paragraphs.map");
  });

  it("takes every paragraph ref from the registry", () => {
    expect(PROSE).toContain("paragraphRef(index)");
    expect(
      PROSE.includes("(node"),
      "ChapterBody declares a function over a paragraph node — a ref built " +
        "during render has a new identity on every render, which is the " +
        "regression this module exists to prevent",
    ).toBe(false);
  });

  it("memoises the prose so a render of the head does not walk it", () => {
    expect(SOURCE).toMatch(/const ChapterBody = memo\(/);
  });

  it("keeps the scroll read-out out of component state", () => {
    expect(
      SOURCE.includes("setPercent"),
      "a percentage in state re-renders every paragraph on every scroll frame",
    ).toBe(false);
  });
});
