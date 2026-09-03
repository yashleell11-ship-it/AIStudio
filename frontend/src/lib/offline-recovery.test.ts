import { describe, expect, it } from "vitest";
import {
  OFFLINE_DOWNLOADS_NOTE,
  OFFLINE_RETRY_COOLDOWN_MS,
  offlineDescription,
  shouldAutoRetry,
} from "./offline-recovery";

const NOW = 1_000_000;

describe("shouldAutoRetry", () => {
  it("retries the first time the connection comes back", () => {
    expect(shouldAutoRetry({ online: true, lastRetryAt: null, now: NOW })).toBe(true);
  });

  it("ignores an event that arrives already offline again", () => {
    expect(shouldAutoRetry({ online: false, lastRetryAt: null, now: NOW })).toBe(false);
  });

  it("swallows a flapping connection inside the cooldown", () => {
    expect(
      shouldAutoRetry({
        online: true,
        lastRetryAt: NOW - (OFFLINE_RETRY_COOLDOWN_MS - 1),
        now: NOW,
      }),
    ).toBe(false);
  });

  it("retries again once the cooldown has elapsed", () => {
    expect(
      shouldAutoRetry({
        online: true,
        lastRetryAt: NOW - OFFLINE_RETRY_COOLDOWN_MS,
        now: NOW,
      }),
    ).toBe(true);
  });

  it("honours a caller-supplied cooldown", () => {
    expect(
      shouldAutoRetry({ online: true, lastRetryAt: NOW - 500, now: NOW, cooldownMs: 100 }),
    ).toBe(true);
    expect(
      shouldAutoRetry({ online: true, lastRetryAt: NOW - 50, now: NOW, cooldownMs: 100 }),
    ).toBe(false);
  });
});

describe("offlineDescription", () => {
  it("appends the one thing that still works to the screen's own lead", () => {
    expect(offlineDescription("Your library needs a connection to load.")).toBe(
      `Your library needs a connection to load. ${OFFLINE_DOWNLOADS_NOTE}`,
    );
  });

  it("does not leave a dangling space for an empty lead", () => {
    expect(offlineDescription("  ")).toBe(OFFLINE_DOWNLOADS_NOTE);
  });
});
