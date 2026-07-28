import { describe, expect, it } from "vitest";
import {
  MOODS,
  MOOD_BASE,
  MOOD_LABELS,
  MOOD_SURFACE,
  MOOD_TINT,
  isTintedMood,
  moodPickerBackground,
  moodShellBackground,
  toMood,
} from "./mood";

describe("mood palette", () => {
  it("defines a label and tint for every mood", () => {
    for (const mood of MOODS) {
      expect(MOOD_LABELS[mood]).toBeTruthy();
      expect(MOOD_TINT[mood]).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it("treats default as untinted (the existing dark base)", () => {
    expect(MOOD_TINT.default).toBe(MOOD_BASE);
    expect(isTintedMood("default")).toBe(false);
  });

  it("treats every non-default mood as tinted", () => {
    for (const mood of MOODS) {
      if (mood === "default") continue;
      expect(isTintedMood(mood)).toBe(true);
    }
  });
});

describe("moodShellBackground", () => {
  it("returns the flat themed surface for the default mood", () => {
    expect(moodShellBackground("default")).toBe(MOOD_SURFACE);
  });

  it("mixes the tint over the themed surface for a tinted mood", () => {
    const bg = moodShellBackground("romantic");
    expect(bg).toContain(MOOD_TINT.romantic);
    expect(bg).toContain(MOOD_SURFACE);
    expect(bg).toContain("color-mix");
  });

  it("never hard-codes the dark base", () => {
    // The shell paints this over everything, so a literal here would survive a
    // theme switch and leave a light theme sitting on a near-black page.
    for (const mood of MOODS) {
      expect(moodShellBackground(mood)).not.toContain(MOOD_BASE);
      expect(moodPickerBackground(mood)).not.toContain(MOOD_BASE);
    }
  });
});

describe("moodPickerBackground", () => {
  it("returns the themed surface for default and a gradient for a tinted mood", () => {
    expect(moodPickerBackground("default")).toBe(MOOD_SURFACE);
    expect(moodPickerBackground("horror")).toContain(MOOD_TINT.horror);
  });
});

describe("toMood", () => {
  it("passes through known moods", () => {
    expect(toMood("fantasy")).toBe("fantasy");
  });

  it("falls back to default for unknown or empty values", () => {
    expect(toMood("sparkly")).toBe("default");
    expect(toMood(null)).toBe("default");
    expect(toMood(undefined)).toBe("default");
  });
});
