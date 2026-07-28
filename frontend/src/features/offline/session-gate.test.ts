import { describe, expect, it } from "vitest";
import { ApiError } from "@/types/api";
import {
  isNetworkUnreachableError,
  isSessionUnresolved,
  resolveSessionGate,
} from "./session-gate";

const NETWORK_ERROR = new ApiError(0, {
  code: "network_error",
  message: "Could not reach the server. Is the backend running?",
});
const UNAUTHORIZED = new ApiError(401, { code: "unauthorized", message: "no" });
const SERVER_ERROR = new ApiError(500, { code: "boom", message: "no" });

describe("isNetworkUnreachableError", () => {
  it("recognises the failure http.ts raises when fetch itself fails", () => {
    expect(isNetworkUnreachableError(NETWORK_ERROR)).toBe(true);
  });

  it("does not mistake a real HTTP answer for one", () => {
    expect(isNetworkUnreachableError(UNAUTHORIZED)).toBe(false);
    expect(isNetworkUnreachableError(SERVER_ERROR)).toBe(false);
    expect(isNetworkUnreachableError(new Error("boom"))).toBe(false);
    expect(isNetworkUnreachableError(null)).toBe(false);
  });
});

describe("resolveSessionGate", () => {
  it("admits a resolved session", () => {
    expect(resolveSessionGate({ isLoading: false, hasUser: true, error: null })).toBe(
      "admit",
    );
  });

  it("waits while the probe is in flight", () => {
    expect(resolveSessionGate({ isLoading: true, hasUser: false, error: null })).toBe(
      "pending",
    );
  });

  it("redirects when the server says there is no session", () => {
    // `useCurrentUser` turns 401 into `null` data, so this is the shape of a
    // genuine "not signed in".
    expect(resolveSessionGate({ isLoading: false, hasUser: false, error: null })).toBe(
      "redirect",
    );
  });

  it("admits offline rather than sending the reader to a login page it cannot load", () => {
    expect(
      resolveSessionGate({ isLoading: false, hasUser: false, error: NETWORK_ERROR }),
    ).toBe("admit-offline");
  });

  it("still redirects when the server answered and the answer was 401", () => {
    expect(
      resolveSessionGate({ isLoading: false, hasUser: false, error: UNAUTHORIZED }),
    ).toBe("redirect");
  });

  it("treats a reachable but broken server as a real answer, not as offline", () => {
    // A 500 means the server is there. Rendering the app on it would hide a
    // genuine outage behind an "offline" story.
    expect(
      resolveSessionGate({ isLoading: false, hasUser: false, error: SERVER_ERROR }),
    ).toBe("redirect");
  });

  it("prefers a known user over any error", () => {
    expect(
      resolveSessionGate({ isLoading: false, hasUser: true, error: NETWORK_ERROR }),
    ).toBe("admit");
  });
});

describe("isSessionUnresolved", () => {
  it("holds the shell back only while there is nothing to render", () => {
    expect(isSessionUnresolved("pending")).toBe(true);
    expect(isSessionUnresolved("redirect")).toBe(true);
    expect(isSessionUnresolved("admit")).toBe(false);
    expect(isSessionUnresolved("admit-offline")).toBe(false);
  });
});
