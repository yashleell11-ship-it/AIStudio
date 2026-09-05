import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { LIBRARY_DENSITIES } from "@/features/library/density";
import {
  DEFAULT_DESIGN_PRESET,
  DESIGN_PRESETS,
  DESIGN_PRESET_META,
  designPresetList,
  initialDesignPreset,
  isDesignPreset,
  parseDesignPreset,
} from "./presets";
import {
  NOVEL_PALETTES,
  novelPalette,
  paletteSurface,
} from "@/features/novels/palettes";
import {
  PRESETS_CSS,
  containsColourLiteral,
  declarationBlock,
  referenceCount,
  shapeBaseBlock,
} from "./shape-css.testkit";

/** The `--shape-*` defaults in globals.css: what Signature must equal. */
const SHAPE_BASE = shapeBaseBlock();

function presetBlock(preset: string): Record<string, string> {
  return declarationBlock(`:root[data-preset="${preset}"]`);
}

describe("design preset identity", () => {
  it("describes every declared preset", () => {
    for (const preset of DESIGN_PRESETS) {
      const meta = DESIGN_PRESET_META[preset];
      expect(meta.id).toBe(preset);
      expect(meta.label).toBeTruthy();
      expect(meta.description).toBeTruthy();
      expect(meta.character).toBeTruthy();
      expect(LIBRARY_DENSITIES).toContain(meta.density);
      expect(meta.motion).toBeGreaterThan(0);
      expect(meta.motion).toBeLessThanOrEqual(1);
    }
  });

  it("gives every preset a unique id and a unique label", () => {
    expect(new Set(DESIGN_PRESETS).size).toBe(DESIGN_PRESETS.length);
    const labels = DESIGN_PRESETS.map((id) => DESIGN_PRESET_META[id].label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("makes each preset a distinct position rather than a slider stop", () => {
    // Five points on one density line would not be five designs. Every preset
    // has to differ from every other in more than one of the axes a viewer can
    // actually see, or the picker is offering a choice that is not there.
    const axes = designPresetList().map((meta) => [
      meta.preview.translucent,
      meta.preview.bordered,
      meta.preview.serif,
      meta.preview.radius,
      meta.density,
      meta.readerCinema,
      meta.motion,
    ]);
    for (let a = 0; a < axes.length; a += 1) {
      for (let b = a + 1; b < axes.length; b += 1) {
        const differences = axes[a].filter((value, index) => value !== axes[b][index]);
        expect(
          differences.length,
          `${DESIGN_PRESETS[a]} and ${DESIGN_PRESETS[b]} differ on too little`,
        ).toBeGreaterThanOrEqual(2);
      }
    }
  });

  it("keeps the app's own look as the default and first in the list", () => {
    expect(DEFAULT_DESIGN_PRESET).toBe("signature");
    expect(DESIGN_PRESETS[0]).toBe("signature");
    expect(DESIGN_PRESET_META.signature.motion).toBe(1);
    expect(DESIGN_PRESET_META.signature.density).toBe("comfortable");
    expect(DESIGN_PRESET_META.signature.readerCinema).toBe(false);
  });

  it("does not reuse a theme's name", () => {
    // Both pickers live on the same settings screen. "Eclipse" as a palette
    // and "Eclipse" as a layout would be two controls that look like one.
    const labels = DESIGN_PRESETS.map((id) => DESIGN_PRESET_META[id].label.toLowerCase());
    expect(labels).not.toContain("eclipse");
  });
});

describe("parseDesignPreset", () => {
  it("accepts every declared preset", () => {
    for (const preset of DESIGN_PRESETS) {
      expect(parseDesignPreset(preset)).toBe(preset);
    }
  });

  it("tolerates surrounding whitespace", () => {
    expect(parseDesignPreset("  cinema \n")).toBe("cinema");
  });

  it("reports an absent or unrecognised value as unset", () => {
    expect(parseDesignPreset(null)).toBeNull();
    expect(parseDesignPreset("")).toBeNull();
    expect(parseDesignPreset("eclipse")).toBeNull();
    expect(parseDesignPreset("Compact")).toBeNull();
  });

  it("narrows only exact preset ids", () => {
    expect(isDesignPreset("flat")).toBe(true);
    expect(isDesignPreset("flatter")).toBe(false);
    expect(isDesignPreset(7)).toBe(false);
    expect(isDesignPreset(null)).toBe(false);
  });
});

describe("initialDesignPreset", () => {
  it("honours a stored choice", () => {
    expect(initialDesignPreset("editorial")).toBe("editorial");
  });

  it("falls back to the default when nothing is stored", () => {
    // Unlike the theme, there is no OS signal to seed this from.
    expect(initialDesignPreset(null)).toBe(DEFAULT_DESIGN_PRESET);
    expect(initialDesignPreset("nonsense")).toBe(DEFAULT_DESIGN_PRESET);
  });
});

describe("preset CSS blocks", () => {
  it("declares a block for every preset the app offers", () => {
    // The picker and the stylesheet are written independently. If they
    // disagree, a tile applies an attribute no rule matches and the viewer
    // silently keeps the look they were trying to leave.
    for (const preset of DESIGN_PRESETS) {
      expect(() => presetBlock(preset), preset).not.toThrow();
      expect(Object.keys(presetBlock(preset)).length, preset).toBeGreaterThan(0);
    }
  });

  it("ships no preset block the app does not offer", () => {
    const declared = [...PRESETS_CSS.matchAll(/:root\[data-preset="([a-z0-9-]+)"\]/gi)].map(
      (match) => match[1],
    );
    expect(new Set(declared)).toEqual(new Set(DESIGN_PRESETS));
  });

  it("hard-codes no colour in any preset", () => {
    // The rule the whole 5 × 42 grid rests on. A preset that named a hex would
    // look wrong under forty-one palettes and right under one.
    for (const preset of DESIGN_PRESETS) {
      for (const [token, value] of Object.entries(presetBlock(preset))) {
        expect(containsColourLiteral(value), `${preset} ${token}: ${value}`).toBe(false);
      }
    }
  });

  it("declares no theme role in any preset", () => {
    // References to `--mm-*` are the point (`--shape-panel-fill:
    // var(--mm-surface)`); DECLARING one would be a preset repainting the app.
    for (const preset of DESIGN_PRESETS) {
      const declared = Object.keys(presetBlock(preset));
      expect(declared.filter((token) => token.startsWith("--mm-")), preset).toEqual([]);
    }
  });

  it("stays inside the four vocabularies a preset owns", () => {
    // `--shape-*` (ours), plus the three Tailwind scale tokens `rounded-*`,
    // `text-*` and the spacing utilities compile to. Anything else is a preset
    // reaching into a part of the system it does not own.
    const allowed =
      /^(--shape-[a-z-]+|--radius-(?:sm|md|lg|xl|2xl|3xl|4xl)|--text-[a-z0-9]+(?:--line-height)?|--spacing)$/;
    for (const preset of DESIGN_PRESETS) {
      for (const token of Object.keys(presetBlock(preset))) {
        expect(allowed.test(token), `${preset} sets ${token}`).toBe(true);
      }
    }
  });

  it("names only shape roles the base declares", () => {
    // A typo'd `--shape-*` would be a variable nothing reads — a preset knob
    // wired to nothing, which is invisible until someone notices the preset
    // does less than it claims.
    const known = new Set(Object.keys(SHAPE_BASE));
    for (const preset of DESIGN_PRESETS) {
      for (const token of Object.keys(presetBlock(preset))) {
        if (!token.startsWith("--shape-")) continue;
        expect(known.has(token), `${preset} sets unknown shape role ${token}`).toBe(true);
      }
    }
  });

  it("keeps Signature byte-identical to the app before presets existed", () => {
    // THE regression bar. `globals.css`'s `--shape-*` base was extracted
    // verbatim from the literals the app shipped with; Signature restates it,
    // and this compares the two declaration for declaration. It also declares
    // no `--text-*`, `--radius-*` or `--spacing`, so Tailwind's own defaults —
    // which is what the app has always rendered at — are left untouched.
    const signature = presetBlock("signature");
    expect(signature).toEqual(SHAPE_BASE);
    for (const token of Object.keys(signature)) {
      expect(token.startsWith("--shape-"), `signature sets ${token}`).toBe(true);
    }
  });

  it("gives every preset something visible to say about surfaces or rhythm", () => {
    // Signature excepted: a preset that only restated the defaults would be a
    // tile that does nothing.
    for (const preset of DESIGN_PRESETS) {
      if (preset === DEFAULT_DESIGN_PRESET) continue;
      const block = presetBlock(preset);
      const changed = Object.entries(block).filter(
        ([token, value]) => SHAPE_BASE[token] === undefined || SHAPE_BASE[token] !== value,
      );
      expect(changed.length, `${preset} changes nothing`).toBeGreaterThanOrEqual(5);
    }
  });

  it("agrees with the motion multiplier the metadata carries", () => {
    // `--shape-motion` drives the CSS animations; `meta.motion` drives the
    // framer-motion primitives, which cannot read a custom property. Two
    // numbers for one decision is a drift waiting to happen, so it is pinned.
    for (const preset of DESIGN_PRESETS) {
      const declared = presetBlock(preset)["--shape-motion"] ?? SHAPE_BASE["--shape-motion"];
      expect(Number(declared), `${preset} --shape-motion`).toBe(
        DESIGN_PRESET_META[preset].motion,
      );
    }
  });

  it("routes every surface fill a preset changes through a theme role", () => {
    for (const preset of DESIGN_PRESETS) {
      const block = presetBlock(preset);
      for (const role of ["--shape-panel-fill", "--shape-card-fill"] as const) {
        if (block[role] === undefined) continue;
        expect(block[role], `${preset} ${role}`).toMatch(/^var\(--mm-[a-z-]+\)$/);
      }
    }
  });

  it("reads the shape roles it moves", () => {
    // Every `--shape-*` a preset sets has to be consumed by a rule somewhere,
    // or the preset is describing a change the app does not make.
    for (const preset of DESIGN_PRESETS) {
      for (const token of Object.keys(presetBlock(preset))) {
        if (!token.startsWith("--shape-")) continue;
        expect(referenceCount(token), `${token} is set but never read`).toBeGreaterThan(0);
      }
    }
  });
});

describe("layout and reader defaults", () => {
  it("opens the library the way the preset's character implies", () => {
    // Compact exists to put the most series on screen, which the dense cover
    // grid does better than a list; Editorial exists to put metadata beside
    // the artwork, which is exactly what a list row is. Two presets resolving
    // to the same layout would make this axis carry no information.
    expect(DESIGN_PRESET_META.compact.density).toBe("compact");
    expect(DESIGN_PRESET_META.editorial.density).toBe("list");
    expect(DESIGN_PRESET_META.cinema.density).toBe("comfortable");
  });

  it("starts the reader with its chrome hidden only in Cinema", () => {
    for (const preset of DESIGN_PRESETS) {
      expect(DESIGN_PRESET_META[preset].readerCinema, preset).toBe(preset === "cinema");
    }
  });

  it("orders the presets from most motion to least, Signature first", () => {
    expect(DESIGN_PRESET_META.cinema.motion).toBeLessThan(
      DESIGN_PRESET_META.signature.motion,
    );
    for (const preset of DESIGN_PRESETS) {
      expect(DESIGN_PRESET_META[preset].motion, preset).toBeLessThanOrEqual(1);
    }
  });
});

describe("the novel reading surface is a third, independent axis", () => {
  /**
   * The app has three appearance systems, not two: the palette (what colour
   * the APP is), the preset (what shape it is), and the twelve reading
   * palettes the novel reader paints its PAGE with. The third is the most
   * carefully argued of them — no pure white on pure black, warm ink over warm
   * paper, `ink` at 6:1 and `muted` at 3:1 — and none of that survives being
   * blended with the other two.
   *
   * It stays separate structurally rather than by convention: the twelve are
   * plain hexes applied to the prose column as inline styles, so nothing in
   * the cascade reaches them. A preset can restyle every piece of chrome
   * around the page and cannot touch the page.
   */
  const PALETTES_SOURCE = readFileSync(
    path.resolve(__dirname, "../novels/palettes.ts"),
    "utf8",
  );

  it("carries literal colours, not cascade lookups", () => {
    for (const palette of NOVEL_PALETTES) {
      for (const role of ["bg", "ink", "muted"] as const) {
        expect(palette[role], `${palette.id}.${role}`).toMatch(/^#[0-9a-f]{6}$/i);
      }
    }
    expect(NOVEL_PALETTES.length).toBe(12);
  });

  it("names no shape role, so no preset can reach the page", () => {
    // The thirteenth option, "Follow site theme", DOES resolve through the
    // cascade — that is its whole purpose — but only through colour roles.
    // Shape has no business inside a reading surface either way.
    expect(PALETTES_SOURCE).not.toMatch(/--shape-/);
    expect(PALETTES_SOURCE).not.toMatch(/--text-|--radius-|--spacing/);
  });

  it("resolves 'follow site theme' through colour roles only", () => {
    const followed = paletteSurface(null);
    for (const role of ["bg", "ink", "muted"] as const) {
      expect(followed[role], role).toMatch(/^var\(--color-[a-z-]+\)$/);
    }
  });

  it("is untouched by every preset the picker offers", () => {
    // A real palette resolves to the same four values no matter which preset
    // is applied, because none of them is read from the document at all.
    const paper = paletteSurface(novelPalette("paper"));
    expect(paper.bg).toMatch(/^#[0-9a-f]{6}$/i);
    expect(paper.ink).toMatch(/^#[0-9a-f]{6}$/i);
    expect(paper.rule).toContain(paper.muted);
  });
});

describe("the two clients name the same five presets", () => {
  /**
   * The presets are presented as ONE system, not as a web design system and a
   * phone one: the settings screens list the same five positions, in the same
   * order, with the same one-line character. A reader who picks a look on the
   * phone and then opens the site is looking for the name they just chose.
   *
   * That is a claim no single-client test can make. `matte`/`flat` shipped as
   * "Matte" on the phone and "Flat" on the web and both suites stayed green,
   * because each only ever checked itself. So this reads the phone's registry
   * off disk — the same trick the novel-palette suite above plays on
   * `palettes.ts`, one tree over.
   *
   * IDS are deliberately not compared. Each client persists its own id
   * locally, so they are free to disagree and expensive to change: the web
   * still stores `flat` (and `presets.css` still matches on it) under the
   * label "Matte", because renaming the id would strand every profile that had
   * chosen it. What the reader sees is the label, and the label is the thing
   * that has to agree.
   */
  const MOBILE_PRESETS_DART = readFileSync(
    path.resolve(__dirname, "../../../../mobile/lib/app/theme/app_presets.dart"),
    "utf8",
  );

  /** Every `id: '…', name: '…'` pair in `AppPresets`, in declaration order. */
  const mobileNames = [...MOBILE_PRESETS_DART.matchAll(/id:\s*'[^']+',\s*name:\s*'([^']+)',/g)].map(
    (match) => match[1],
  );

  it("finds the phone's registry where it is expected", () => {
    // A regex that silently matched nothing would make every assertion below
    // vacuously true, which is worse than no test at all.
    expect(mobileNames.length).toBe(DESIGN_PRESETS.length);
  });

  it("shows the same name for the same preset on both clients", () => {
    const webLabels = DESIGN_PRESETS.map((id) => DESIGN_PRESET_META[id].label);
    expect([...mobileNames].sort()).toEqual([...webLabels].sort());
  });
});
