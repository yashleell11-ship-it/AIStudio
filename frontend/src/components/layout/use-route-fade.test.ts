import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { ROUTE_FADE_CLASS, shouldFadeRoute } from "./use-route-fade";

describe("shouldFadeRoute", () => {
  it("fades an ordinary page", () => {
    for (const path of [
      "/library",
      "/library/browse",
      "/library/collections",
      "/library/statistics",
      "/sources",
      "/sources/mangadex",
      "/updates",
      "/settings",
      "/search",
      "/downloads",
    ]) {
      expect(shouldFadeRoute(path), path).toBe(true);
    }
  });

  it("never fades inside a reader", () => {
    // A route change here is usually the next chapter, and dimming the page
    // being read at every chapter boundary is the one place this animation
    // would be actively unwanted.
    for (const path of [
      "/reader/mangadex/solo-leveling/1",
      "/reader/aurorascans/x/x/chapters/chapter-1",
      "/read-all/mangadex/solo-leveling",
      "/novels/royalroad/some-book/ch-1",
    ]) {
      expect(shouldFadeRoute(path), path).toBe(false);
    }
  });

  it("fades the reader landing, which is a page and not a reader", () => {
    expect(shouldFadeRoute("/reader")).toBe(true);
  });
});

describe("the animation this hook drives", () => {
  const css = readFileSync(
    join(process.cwd(), "src", "app", "globals.css"),
    "utf8",
  );

  it("exists under the class the hook toggles", () => {
    expect(css).toContain(`.${ROUTE_FADE_CLASS} {`);
  });

  it("rides the preset multiplier like every other duration", () => {
    expect(css).toMatch(
      new RegExp(`\\.${ROUTE_FADE_CLASS} \\{[\\s\\S]*?var\\(--shape-motion\\)`),
    );
  });

  it("declares no fill mode, so a page is visible when it does not run", () => {
    // `both` would leave the app's only scroller stuck at its `from` opacity
    // in a paused tab, an old browser, or any frame the animation never got.
    const rule = css.slice(css.indexOf(`.${ROUTE_FADE_CLASS} {`));
    expect(rule.slice(0, rule.indexOf("}"))).not.toMatch(
      /\b(both|forwards|backwards)\b/,
    );
  });

  it("animates opacity only, never a transform on the scroller", () => {
    // A transform on `main` makes it the containing block for every fixed
    // descendant, which silently moves the bulk action bar and the tab pill.
    const frames = css.slice(css.indexOf("@keyframes route-in"));
    const body = frames.slice(0, frames.indexOf("\n}"));
    expect(body).not.toContain("transform");
    expect(body).toContain("opacity");
  });
});
