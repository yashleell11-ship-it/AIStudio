import { describe, expect, it } from "vitest";
import type { BootstrapStatus } from "@/features/auth/types";
import type { SourceSummary } from "@/features/sources/types";
import {
  resolveNovelSource,
  resolveNovelsEnabled,
  sourceKindsKnown,
} from "./gate";

function status(overrides: Partial<BootstrapStatus> = {}): BootstrapStatus {
  return {
    needs_bootstrap: false,
    registration_enabled: false,
    ...overrides,
  };
}

function source(overrides: Partial<SourceSummary> = {}): SourceSummary {
  return {
    id: "asurascans",
    name: "Asura Scans",
    description: "",
    browsable: true,
    supports_import: true,
    ...overrides,
  };
}

const MANGA = source();
const NOVEL = source({ id: "royalroad", content_kind: "novel" });
const LISTING = [MANGA, NOVEL];

describe("resolveNovelsEnabled", () => {
  it("does not answer while the bootstrap probe is in flight", () => {
    expect(resolveNovelsEnabled(undefined, true)).toBeUndefined();
  });

  it("answers on once the flag has arrived", () => {
    expect(resolveNovelsEnabled(status({ novels_enabled: true }), false)).toBe(true);
  });

  it("answers off once the flag has arrived", () => {
    expect(resolveNovelsEnabled(status({ novels_enabled: false }), false)).toBe(false);
  });

  it("reads a backend that never sends the flag as off, not as unknown", () => {
    expect(resolveNovelsEnabled(status(), false)).toBe(false);
  });

  it("reads a probe that settled without data as off", () => {
    expect(resolveNovelsEnabled(undefined, false)).toBe(false);
  });
});

describe("sourceKindsKnown", () => {
  it("knows nothing until the novels flag does", () => {
    expect(sourceKindsKnown(undefined, undefined)).toBe(false);
    expect(sourceKindsKnown(undefined, LISTING)).toBe(false);
  });

  it("needs no listing on a deployment with novels off", () => {
    expect(sourceKindsKnown(false, undefined)).toBe(true);
  });

  it("waits for the listing on a deployment with novels on", () => {
    expect(sourceKindsKnown(true, undefined)).toBe(false);
    expect(sourceKindsKnown(true, LISTING)).toBe(true);
  });
});

describe("resolveNovelSource", () => {
  it("does not guess while the novels flag is unknown", () => {
    expect(resolveNovelSource(undefined, undefined, "royalroad")).toBeUndefined();
    expect(resolveNovelSource(undefined, LISTING, "royalroad")).toBeUndefined();
  });

  it("says pages immediately when novels are off", () => {
    expect(resolveNovelSource(false, undefined, "royalroad")).toBe(false);
  });

  it("does not guess while the listing is still loading", () => {
    expect(resolveNovelSource(true, undefined, "royalroad")).toBeUndefined();
  });

  it("reads the medium off the listing", () => {
    expect(resolveNovelSource(true, LISTING, "royalroad")).toBe(true);
    expect(resolveNovelSource(true, LISTING, "asurascans")).toBe(false);
  });

  it("reads a source the listing does not carry as pages", () => {
    expect(resolveNovelSource(true, LISTING, "uninstalled")).toBe(false);
  });
});
