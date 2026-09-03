import { describe, expect, it } from "vitest";
import { ApiError } from "@/types/api";
import { apiErrorMessage, resolveViewState } from "./view-state";

const NETWORK_ERROR = new ApiError(0, {
  code: "network_error",
  message: "Can't reach ManhwaManiacs right now. Check your connection and try again.",
});
const SERVER_ERROR = new ApiError(500, { code: "boom", message: "Something broke." });

describe("resolveViewState", () => {
  it("reports loading first, regardless of error or emptiness", () => {
    expect(
      resolveViewState({ isLoading: true, error: SERVER_ERROR, isEmpty: true }),
    ).toBe("loading");
  });

  it("distinguishes an unreachable server from a real error response", () => {
    expect(
      resolveViewState({ isLoading: false, error: NETWORK_ERROR, isEmpty: true }),
    ).toBe("offline");
    expect(
      resolveViewState({ isLoading: false, error: SERVER_ERROR, isEmpty: true }),
    ).toBe("error");
  });

  it("reports empty only once loading and error are both ruled out", () => {
    expect(
      resolveViewState({ isLoading: false, error: null, isEmpty: true }),
    ).toBe("empty");
  });

  it("reports content when data arrived and isn't empty", () => {
    expect(
      resolveViewState({ isLoading: false, error: null, isEmpty: false }),
    ).toBe("content");
  });

  it("an error outranks emptiness — never shows 'nothing here' for a failed request", () => {
    expect(
      resolveViewState({ isLoading: false, error: SERVER_ERROR, isEmpty: true }),
    ).toBe("error");
  });
});

describe("apiErrorMessage", () => {
  it("surfaces the ApiError's own UI-safe message", () => {
    expect(apiErrorMessage(SERVER_ERROR, "fallback")).toBe("Something broke.");
  });

  it("falls back for anything that isn't an ApiError, never stringifying it", () => {
    expect(apiErrorMessage(new Error("raw stack-shaped thing"), "fallback")).toBe(
      "fallback",
    );
    expect(apiErrorMessage("weird thrown string", "fallback")).toBe("fallback");
    expect(apiErrorMessage(null, "fallback")).toBe("fallback");
  });
});
