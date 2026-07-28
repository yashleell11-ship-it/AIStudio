import { describe, expect, it } from "vitest";
import { decodeRouteParam } from "./route-params";

describe("decodeRouteParam", () => {
  it("restores a connector id containing a slash", () => {
    // Madara sources use ids like `series/chapter-1`. Left encoded, every link
    // builder encoded it again and the page showed a different series.
    expect(decodeRouteParam("manga%2Fsolo-leveling")).toBe("manga/solo-leveling");
  });

  it("restores non-ascii ids", () => {
    expect(decodeRouteParam("caf%C3%A9")).toBe("café");
  });

  it("leaves an already-decoded id alone", () => {
    expect(decodeRouteParam("solo-leveling")).toBe("solo-leveling");
  });

  it("returns the raw value rather than throwing on a malformed sequence", () => {
    // A bare % is not a valid escape; a crashed route is worse than a not-found.
    expect(decodeRouteParam("100%")).toBe("100%");
  });
});
