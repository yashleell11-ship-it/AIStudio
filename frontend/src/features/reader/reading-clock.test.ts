import { describe, expect, it } from "vitest";
import { elapsedSince, MAX_PUSH_SECONDS } from "./reading-clock";

const T = 1_700_000_000_000;

describe("elapsedSince", () => {
  it("reports whole seconds between two pushes", () => {
    expect(elapsedSince(T, T + 42_000)).toBe(42);
    // Partial seconds floor rather than round: a push cannot claim time that
    // has not happened.
    expect(elapsedSince(T, T + 42_900)).toBe(42);
  });

  it("reports nothing before the clock has started", () => {
    expect(elapsedSince(null, T)).toBe(0);
  });

  it("reports nothing for a clock that went backwards", () => {
    // An NTP correction or a waking device, not negative reading.
    expect(elapsedSince(T, T - 60_000)).toBe(0);
    expect(elapsedSince(T, T)).toBe(0);
  });

  it("refuses to bill an idle gap as reading", () => {
    // A chapter left open overnight: the cap, not nine hours.
    expect(elapsedSince(T, T + 9 * 60 * 60 * 1000)).toBe(MAX_PUSH_SECONDS);
    expect(elapsedSince(T, T + (MAX_PUSH_SECONDS + 1) * 1000)).toBe(MAX_PUSH_SECONDS);
    expect(elapsedSince(T, T + MAX_PUSH_SECONDS * 1000)).toBe(MAX_PUSH_SECONDS);
  });

  it("ignores a non-finite instant rather than sending NaN", () => {
    expect(elapsedSince(Number.NaN, T)).toBe(0);
    expect(elapsedSince(T, Number.POSITIVE_INFINITY)).toBe(0);
  });
});
