import { describe, expect, it } from "vitest";
import { shelfCountLine } from "./count-line";

describe("shelfCountLine", () => {
  it("never doubles the s on 'series', which is already plural", () => {
    // The bug this module exists for: "22 seriess followed".
    expect(shelfCountLine(22, false)).toBe("22 series followed");
    expect(shelfCountLine(0, false)).toBe("0 series followed");
  });

  it("keeps 'series' unchanged in the singular", () => {
    expect(shelfCountLine(1, false)).toBe("1 series followed");
  });

  it("pluralises 'novel', which is not its own plural", () => {
    expect(shelfCountLine(1, true)).toBe("1 novel on your shelf");
    expect(shelfCountLine(3, true)).toBe("3 novels on your shelf");
    expect(shelfCountLine(0, true)).toBe("0 novels on your shelf");
  });
});
