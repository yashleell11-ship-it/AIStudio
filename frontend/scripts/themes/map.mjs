/**
 * base16 → ManhwaManiacs role mapping, and the contrast gate that decides
 * whether a scheme is shippable.
 *
 * ## Why a mapping at all
 *
 * base16 is a SYNTAX-HIGHLIGHTING spec: sixteen slots, eight of them named
 * after token classes (red/orange/yellow/green/cyan/blue/magenta/brown). An app
 * chrome needs different things — a page, two raised surfaces, body text,
 * secondary text, one accent that carries identity, one that supports it, three
 * status colours, and a pile of derived washes. So the sixteen bases are read
 * for what the spec says they MEAN (base00 is the page, base05 is the text,
 * base08 is the error red) and the rest of the app's tokens are derived from
 * those in the ratios the shipped Eclipse palette established — never invented
 * per scheme, which is what would make forty themes look like forty different
 * apps.
 *
 * ## Why derivation, and where it stops
 *
 * Plenty of beloved schemes are unreadable at app scale. Nord's `base03`
 * comment grey is 1.9:1 on its own surfaces; Solarized Light's yellow is 1.9:1
 * on its paper. A terminal gets away with that because the failing colour is a
 * comment you are not reading. A library grid does not.
 *
 * So a token that misses its floor is walked along the SCHEME'S OWN foreground
 * ramp (toward `base07`, the far end of the bg→fg gradient in both variants)
 * until it clears — the same move the mobile palettes made by hand, and one
 * that keeps the hue family. Each walk is capped. A scheme that cannot be made
 * legible inside those caps is REJECTED rather than shipped bent out of shape:
 * the point of the gate is that not all 338 deserve to ship.
 */

// ---------------------------------------------------------------------------
// colour maths (a standalone copy of src/lib/contrast.ts — this file runs in
// plain node at build time, and src/ is TypeScript)
// ---------------------------------------------------------------------------

/** `#rrggbb` → `{r,g,b}`. */
export function parseHex(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) throw new Error(`not a hex colour: ${hex}`);
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

export function toHex({ r, g, b }) {
  const part = (v) =>
    Math.max(0, Math.min(255, Math.round(v)))
      .toString(16)
      .padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`.toUpperCase();
}

function channel(value) {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex) {
  const { r, g, b } = parseHex(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG contrast ratio between two opaque hexes, 1–21. */
export function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Linear sRGB mix: `amount` of `b` into `a`. */
export function mix(a, b, amount) {
  const x = parseHex(a);
  const y = parseHex(b);
  return toHex({
    r: x.r + (y.r - x.r) * amount,
    g: x.g + (y.g - x.g) * amount,
    b: x.b + (y.b - x.b) * amount,
  });
}

/** `rgba(...)` from a hex, for the translucent roles (borders, glass, washes). */
export function rgba(hex, alpha) {
  const { r, g, b } = parseHex(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** The worst ratio a colour achieves against any of `backgrounds`. */
function worst(color, backgrounds) {
  return Math.min(...backgrounds.map((bg) => contrast(color, bg)));
}

/**
 * CIE L*, 0–100 — perceived lightness.
 *
 * Used only where the question is "can a reader SEE that these two greys are
 * different", which the contrast ratio answers badly: #504945 and #665C54 are a
 * clearly visible step apart yet score 1.35:1, while two pale greys can score
 * the same and be indistinguishable. Contrast ratio is the right tool for
 * legibility and the wrong one for separation.
 */
export function lightness(hex) {
  const y = luminance(hex);
  return y > 216 / 24389 ? 116 * Math.cbrt(y) - 16 : (24389 / 27) * y;
}

/**
 * The far end of the scheme's own background→foreground ramp: whichever of
 * base00–base07 sits furthest from the page in luminance.
 *
 * NOT simply `base07`. The spec calls base07 "lighter foreground", but the
 * corpus does not honour that — Nord's port puts the frost teal #8FBCBB there
 * and its true ramp end is base06. Picking by measurement instead of by slot is
 * what keeps "walk this colour until it is readable" pointing at the light end
 * of a dark scheme and the dark end of a light one.
 */
function rampEnd(p) {
  const base = luminance(p.base00);
  let best = p.base00.toUpperCase();
  let bestDistance = 0;
  for (let i = 0; i <= 7; i += 1) {
    const value = p[`base0${i}`].toUpperCase();
    const distance = Math.abs(luminance(value) - base);
    if (distance > bestDistance) {
      bestDistance = distance;
      best = value;
    }
  }
  return best;
}

// ---------------------------------------------------------------------------
// gate thresholds
// ---------------------------------------------------------------------------

/**
 * WCAG 2.1 AA. `MUTED` is deliberately the body-text figure and not the 3:1
 * large-text one: `text-muted` is the app's second-most-used colour and it
 * carries chapter numbers, source names and card descriptions at 12–14px. The
 * shipped hand-written palettes already hold that line (see
 * `theme-contrast.test.ts`), and a generated palette is not allowed to be the
 * reason the floor drops.
 */
export const FLOOR = {
  TEXT: 4.5,
  MUTED: 4.5,
  ACCENT: 4.5,
  NON_TEXT: 3,
  /** Both stops of the clipped-gradient `.hero-heading`, which is display-sized. */
  HERO: 3,
};

/**
 * How far a token may be walked before the scheme stops being itself.
 *
 * Foreground and accent roles get a short leash: they are the colours a viewer
 * recognises a scheme BY, and a Gruvbox whose blue has been dragged 40% toward
 * cream is not Gruvbox. Status colours get a longer one because every light
 * scheme in existence fails here — a mid-tone yellow simply cannot sit on paper
 * at 4.5:1 — and the shipped Sepia/Daylight palettes already solved it the same
 * way (#F59E0B amber → #854D0E on paper).
 */
const CAP = { fg: 0.3, muted: 0.45, accent: 0.35, status: 0.6 };

/**
 * Walk `color` toward `target` in 5% steps until it clears `min` against every
 * background. Returns the adjusted colour and how far it travelled, or `null`
 * when the cap is reached first.
 */
function lift(color, backgrounds, min, target, cap) {
  if (worst(color, backgrounds) >= min) return { value: color.toUpperCase(), drift: 0 };
  const steps = Math.round(cap / 0.05);
  for (let step = 1; step <= steps; step += 1) {
    const amount = step * 0.05;
    const candidate = mix(color, target, amount);
    if (worst(candidate, backgrounds) >= min) {
      return { value: candidate, drift: Number(amount.toFixed(2)) };
    }
  }
  return null;
}

/**
 * How far a colour may sit from the page before it stops being a *surface*.
 *
 * base01 and base02 are documented as "lighter background" and "selection
 * background", but a third of the corpus treats base02 as a mid-tone highlight
 * — Solarized's base02 is #586e75, a grey you could set body text in. Used as a
 * panel it would make every card in the app glow. Eclipse's own surfaces sit at
 * 1.10:1 and 1.24:1 from the page, and the light palettes at 1.07 and 1.13; a
 * candidate past this bound is not what the app means by a surface, so the
 * elevation is derived from the page instead — a lift toward the foreground, in
 * the ratio the `bg-white/5` overlays the components already use assume.
 */
const SURFACE_BOUND = 1.45;

/**
 * The page → surface → elevated ramp.
 *
 * **Elevation goes toward light, in every theme.** That is Eclipse's rule
 * (#0A0A0A → #111111 → #181818) and its light palettes' rule too (#EFEDE9 →
 * #F7F5F2 → #FCFBF9), and the app is built on it: components lift themselves
 * with `bg-white/5` overlays that read as a rise on one and as nothing at all
 * on the other. base16 dark schemes agree — base01/base02 climb away from
 * base00 — so their own tones are used. base16 LIGHT schemes go the opposite
 * way, darkening base01/base02 toward the text, which both inverts the app's
 * elevation language and eats the very contrast headroom secondary text needs
 * on a card. Those get a ramp derived toward white, keeping the page's hue as
 * the only thing that carries identity at these luminances anyway.
 *
 * Always monotonic: `theme-contrast.test.ts` asserts elevated steps further
 * from the page than surface does, because that ordering is the only thing
 * making a sheet on a card on a page read as three layers.
 */
function surfaceRamp(p, bg, fg, isDark) {
  const notes = [];
  const usable = (candidate) => {
    const step = contrast(candidate, bg);
    return (
      lightness(candidate) > lightness(bg) && step >= 1.03 && step <= SURFACE_BOUND
    );
  };

  if (!isDark) {
    // A light scheme has nothing lighter than its own page to rise into, so the
    // ramp is derived toward white — measured, not assumed: a page that is
    // already #F8F8F8 has no room up there, and the step has to come back down
    // instead or panels and page are the same colour.
    const up = { surface: mix(bg, "#FFFFFF", 0.35), elevated: mix(bg, "#FFFFFF", 0.72) };
    if (contrast(up.surface, bg) >= 1.03) {
      notes.push("surfaces derived toward white (base01/base02 descend into the text)");
      return { ...up, notes };
    }
    notes.push("surfaces derived downward (the page is already white)");
    return { surface: mix(bg, fg, 0.04), elevated: mix(bg, fg, 0.085), notes };
  }

  let surface = p.base01.toUpperCase();
  if (!usable(surface)) {
    surface = mix(bg, fg, 0.05);
    notes.push("surface derived (base01 is not a panel tone)");
  }
  let elevated = p.base02.toUpperCase();
  if (!usable(elevated) || contrast(elevated, bg) <= contrast(surface, bg) * 1.02) {
    elevated = mix(surface, fg, 0.07);
    notes.push("elevated derived (base02 is a selection tone, not a panel)");
  }
  return { surface, elevated, notes };
}

/**
 * Secondary text: the dimmest tone on the scheme's OWN neutral ramp that still
 * clears the body-text floor on all three surfaces.
 *
 * base04 is the spec's answer ("dark foreground / status bars") and is used
 * verbatim whenever it is both legible and visibly below the body colour. It
 * often is neither: Catppuccin's base04 is 2.4:1 on its own page, while Nord's
 * is 1.11:1 away from base05 — indistinguishable from body text. So the
 * fallback searches the base05 → base03 segment (body text → comment grey,
 * which is the same neutral ramp the scheme drew base04 from) and takes the
 * dimmest passing point. That keeps the hue and gives back the hierarchy;
 * inventing a grey would do neither.
 */
function mutedTone(p, fg, surfaces) {
  const base04 = p.base04.toUpperCase();
  // Eight L* points is roughly where a step between two greys stops being
  // arguable and starts being visible. Nord's base04 is 4.4 from its base05 —
  // the two are the same colour to a reader, which is why Nord ships here with
  // a derived secondary rather than the one the port declares.
  const distinct = (c) => Math.abs(lightness(c) - lightness(fg)) >= 8;
  if (worst(base04, surfaces) >= FLOOR.MUTED && distinct(base04)) {
    return { value: base04, note: null };
  }
  let dimmest = null;
  for (let step = 20; step >= 0; step -= 1) {
    const candidate = mix(fg, p.base03.toUpperCase(), step * 0.05);
    if (worst(candidate, surfaces) >= FLOOR.MUTED) {
      dimmest = { value: candidate, amount: step * 0.05 };
      break;
    }
  }
  if (!dimmest || !distinct(dimmest.value)) return null;
  return {
    value: dimmest.value,
    note: `muted derived ${Math.round(dimmest.amount * 100)}% along base05→base03`,
  };
}

/**
 * The base16 accent slots in the order this app wants them.
 *
 * base0D (blue) leads because it is the spec's own choice for functions and
 * links — the interactive colour. Yellow and orange follow rather than cyan,
 * which is both what warm schemes are recognised by (Gruvbox is not a blue) and
 * what the app's own Eclipse amber has always been. Red comes last: the app
 * already spends it on `--mm-danger`, and a primary that means "error"
 * everywhere else is a primary nobody trusts.
 */
const PRIMARY_ORDER = ["base0D", "base0A", "base09", "base0C", "base0E", "base0B", "base08"];

/**
 * The most a leading accent may be nudged before another slot is preferred
 * instead. Nord's frost blue needs 5% and keeps the job; Gruvbox's blue needs
 * 20%, which is a drag — and Gruvbox has a yellow sitting there at 9:1 that is
 * far more what anyone means by "Gruvbox" anyway.
 */
const GENTLE_LIFT = 0.15;
/** The supporting accent wants a different hue from the primary; magenta first. */
const ACCENT_ORDER = ["base0E", "base0C", "base09", "base0D", "base0B", "base0A", "base08"];

/** Hue angle in degrees, or `null` for a grey (which has no hue to compare). */
function hue(hex) {
  const { r, g, b } = parseHex(hex);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (max === min) return null;
  const d = max - min;
  const raw =
    max === r ? (g - b) / d : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return ((raw * 60) % 360 + 360) % 360;
}

/** Shortest angle between two hues; greys are treated as maximally distant. */
function hueGap(a, b) {
  const ha = hue(a);
  const hb = hue(b);
  if (ha === null || hb === null) return 180;
  const delta = Math.abs(ha - hb) % 360;
  return Math.min(delta, 360 - delta);
}

/**
 * First slot in `order` whose colour clears `min` on every surface.
 *
 * `minHueGap` keeps the supporting accent off the primary's hue. Without it
 * Gruvbox ships an aqua primary beside a green accent and the two read as one
 * colour someone got wrong twice; the app spends them on genuinely different
 * jobs (active nav vs. the ember highlight) and they have to be tellable apart.
 */
function pickAccent(palette, order, backgrounds, min, against, minHueGap = 0) {
  for (const slot of order) {
    const value = palette[slot];
    if (against && value.toLowerCase() === against.toLowerCase()) continue;
    if (against && hueGap(value, against) < minHueGap) continue;
    if (worst(value, backgrounds) >= min) return { slot, value: value.toUpperCase() };
  }
  return null;
}

/**
 * Map one base16 scheme onto the full `--mm-*` role set.
 *
 * Returns `{ ok: true, roles, notes }` or `{ ok: false, reason }`. `notes`
 * records every token that had to be walked and by how much, so the audit can
 * show what was changed rather than quietly shipping it.
 */
export function mapScheme(scheme) {
  const p = scheme.palette;
  const isDark = scheme.variant === "dark";
  const notes = [];

  const bg = p.base00.toUpperCase();

  // The direction "more readable" points in, in the scheme's own tint.
  const target = rampEnd(p);

  // The ramp is laid out from the unlifted body colour — it only needs the
  // direction — and the body colour is then measured against the surfaces the
  // app will actually draw, not against base02, which is often not a surface.
  const ramp = surfaceRamp(p, bg, p.base05.toUpperCase(), isDark);
  notes.push(...ramp.notes);
  const { surface, elevated } = ramp;
  const surfaces = [bg, surface, elevated];

  const fgLift = lift(p.base05.toUpperCase(), surfaces, FLOOR.TEXT, target, CAP.fg);
  if (!fgLift) {
    return { ok: false, reason: "body text cannot reach 4.5:1 on its own surfaces" };
  }
  if (fgLift.drift) notes.push(`body text lifted ${fgLift.drift * 100}% along its own ramp`);
  const fg = fgLift.value;

  const muted = mutedTone(p, fg, surfaces);
  if (!muted) {
    return { ok: false, reason: "no tone sits below body text and still clears 4.5:1" };
  }
  if (muted.note) notes.push(muted.note);

  /**
   * The accent, in order of how much of the scheme's identity it keeps.
   *
   * A NUDGE beats a substitution. Nord's frost blue reads 4.31:1 on its own
   * selection grey — it misses AA by four hundredths — and swapping in the
   * aurora yellow because of that ships a Nord with no frost in it. A 5% step
   * along the scheme's own ramp fixes the number and nobody can tell. Only when
   * the leading slot cannot be rescued inside the cap does another hue get the
   * job, and that is worth recording in the notes.
   */
  const chooseAccent = (order, against, minGap) => {
    const eligible = order.filter(
      (slot) => !against || hueGap(p[slot], against) >= minGap,
    );
    // Two passes down the preference list. The first allows only a nudge, so a
    // slot that is nearly readable keeps its place ahead of one further down;
    // the second allows the full cap, which is where a scheme that put nothing
    // usable near the front finally gives up its lead colour.
    for (const cap of [GENTLE_LIFT, CAP.accent]) {
      for (const slot of eligible) {
        const walked = lift(p[slot].toUpperCase(), surfaces, FLOOR.ACCENT, target, cap);
        if (walked) return { slot, value: walked.value, drift: walked.drift };
      }
    }
    return null;
  };

  const primaryPick = chooseAccent(PRIMARY_ORDER, null, 0);
  if (!primaryPick) return { ok: false, reason: "no accent reaches 4.5:1 on all three surfaces" };
  const primary = primaryPick.value;
  if (primaryPick.slot !== "base0D") {
    notes.push(`primary from ${primaryPick.slot} (base0D unusable)`);
  }
  if (primaryPick.drift) {
    notes.push(`primary lifted ${primaryPick.drift * 100}% along its own ramp`);
  }

  const accentPick = chooseAccent(ACCENT_ORDER, primary, 40) ?? chooseAccent(ACCENT_ORDER, primary, 0);
  const accent = accentPick ? accentPick.value : primary;
  if (!accentPick) notes.push("no second readable accent; reusing primary");
  else if (accentPick.drift) {
    notes.push(`accent lifted ${accentPick.drift * 100}% along its own ramp`);
  }

  /**
   * Text drawn ON a filled accent.
   *
   * The scheme's own ramp ends are tried first and pure black/white only if
   * neither clears the floor. Ranking all six together would pick #000000 over
   * a scheme's near-black for a tenth of a contrast point, and a button label
   * in a colour the palette does not contain is exactly the small wrongness
   * that makes a generated theme look generated.
   */
  const onColor = (base) => {
    const ranked = (candidates) =>
      candidates
        .map((c) => c.toUpperCase())
        .map((c) => ({ c, ratio: contrast(c, base) }))
        .reduce((a, b) => (b.ratio > a.ratio ? b : a));
    const own = ranked([p.base00, p.base07, p.base06, p.base05]);
    if (own.ratio >= FLOOR.TEXT) return own.c;
    const absolute = ranked(["#ffffff", "#000000"]);
    return absolute.ratio >= FLOOR.TEXT ? absolute.c : null;
  };

  const primaryFg = onColor(primary);
  if (!primaryFg) return { ok: false, reason: "no legible label colour for a filled primary button" };

  // Hover moves the accent toward the foreground: brighter on a dark scheme,
  // deeper on a light one, hue intact. Held to the same label contrast so a
  // button does not become unreadable mid-hover.
  let primaryHover = mix(primary, fg, 0.2);
  if (contrast(primaryFg, primaryHover) < FLOOR.TEXT) primaryHover = primary;

  const accentFg = onColor(accent);
  if (!accentFg) return { ok: false, reason: "no legible label colour for a filled accent" };

  // Status colours: the spec's own red/green/yellow, walked onto the page when
  // they are too pale for it. This is where light schemes always need help.
  const status = {};
  for (const [role, slot] of [
    ["danger", "base08"],
    ["success", "base0B"],
    ["warning", "base0A"],
  ]) {
    const lifted = lift(p[slot].toUpperCase(), [bg], FLOOR.TEXT, target, CAP.status);
    if (!lifted) return { ok: false, reason: `${role} (${slot}) cannot reach 4.5:1 on the page` };
    if (lifted.drift) notes.push(`${role} lifted ${lifted.drift * 100}% along its own ramp`);
    status[role] = lifted.value;
  }

  // The inverted band (`ContrastSection`, `.bg-bg-light`). base00 and base07
  // are the two ends of the ramp, so swapping them is always a true inversion
  // of the page in either variant.
  const contrastBg = target;
  const contrastFg = bg;
  if (contrast(contrastFg, contrastBg) < FLOOR.TEXT) {
    return { ok: false, reason: "the scheme's own ramp is too flat for an inverted band" };
  }

  // Borders are a wash of the foreground, as in Eclipse. Light palettes need a
  // heavier one: a 12% dark line on paper is invisible where a 12% light line
  // on near-black is not.
  const borderAlpha = isDark ? 0.14 : 0.18;

  const roles = {
    "--mm-bg": bg,
    "--mm-surface": surface,
    "--mm-elevated": elevated,
    "--mm-fg": fg,
    "--mm-muted": muted.value,
    "--mm-border": rgba(fg, borderAlpha),

    "--mm-contrast-bg": contrastBg,
    "--mm-contrast-fg": contrastFg,
    "--mm-contrast-border": rgba(contrastFg, 0.16),

    "--mm-primary": primary,
    "--mm-primary-hover": primaryHover,
    "--mm-primary-fg": primaryFg,
    "--mm-primary-tint": mix(primary, target, 0.3),
    "--mm-accent": accent,
    "--mm-accent-fg": accentFg,
    "--mm-accent-warm": p.base09.toUpperCase(),

    "--mm-danger": status.danger,
    "--mm-success": status.success,
    "--mm-warning": status.warning,

    "--mm-glass-panel": rgba(surface, 0.72),
    "--mm-glass-card": rgba(elevated, 0.62),
    "--mm-glass-border": rgba(fg, 0.1),
    // `.hero-heading` is clipped-gradient display text. Running it from the
    // accent to the body colour reads as deliberate in every scheme and, since
    // both ends already cleared 4.5:1 on the page, clears the 3:1 large-text
    // floor for free.
    "--mm-hero-from": primary,
    "--mm-hero-to": fg,
    "--mm-scrollbar": rgba(muted.value, 0.35),
    "--mm-scrollbar-hover": rgba(muted.value, 0.55),
    "--mm-glow": isDark
      ? `0 0 24px ${rgba(primary, 0.22)}`
      : `0 2px 16px ${rgba(primary, 0.18)}`,
    "--mm-glass-shadow": isDark
      ? "0 8px 32px rgba(0, 0, 0, 0.37)"
      : `0 8px 24px ${rgba(fg, 0.12)}`,
    "--mm-focus": primary,
  };

  return { ok: true, roles, notes, scheme: isDark ? "dark" : "light" };
}

/**
 * Re-check a mapped role set against every floor the shipped suite asserts.
 *
 * Belt and braces on purpose: `mapScheme` derives, this judges. A derivation
 * bug that produced a plausible-looking hex would otherwise ship, because the
 * only other reviewer of a colour is a human squinting at a diff.
 */
export function verifyRoles(roles) {
  const failures = [];
  const surfaces = ["--mm-bg", "--mm-surface", "--mm-elevated"];
  const check = (label, ratio, min) => {
    if (ratio < min) failures.push(`${label} ${ratio.toFixed(2)}:1 < ${min}:1`);
  };
  // Translucent roles are flattened over what they sit on, which is what the
  // browser draws — scoring the raw rgba would pass invisible hairlines.
  const flatten = (value, over) => {
    const m = /^rgba\((\d+), (\d+), (\d+), ([0-9.]+)\)$/.exec(value);
    if (!m) return value;
    const [r, g, b, a] = m.slice(1).map(Number);
    const back = parseHex(over);
    return toHex({
      r: r * a + back.r * (1 - a),
      g: g * a + back.g * (1 - a),
      b: b * a + back.b * (1 - a),
    });
  };

  for (const surface of surfaces) {
    check(`fg on ${surface}`, contrast(roles["--mm-fg"], roles[surface]), FLOOR.TEXT);
    check(`muted on ${surface}`, contrast(roles["--mm-muted"], roles[surface]), FLOOR.MUTED);
    check(`primary on ${surface}`, contrast(roles["--mm-primary"], roles[surface]), FLOOR.ACCENT);
    check(`focus on ${surface}`, contrast(roles["--mm-focus"], roles[surface]), FLOOR.NON_TEXT);
    const border = flatten(roles["--mm-border"], roles[surface]);
    if (contrast(border, roles[surface]) <= 1.1) {
      failures.push(`border invisible on ${surface}`);
    }
  }
  check(
    "primary-fg on primary",
    contrast(roles["--mm-primary-fg"], roles["--mm-primary"]),
    FLOOR.TEXT,
  );
  check(
    "primary-fg on primary-hover",
    contrast(roles["--mm-primary-fg"], roles["--mm-primary-hover"]),
    FLOOR.TEXT,
  );
  check("accent-fg on accent", contrast(roles["--mm-accent-fg"], roles["--mm-accent"]), FLOOR.TEXT);
  check(
    "contrast band",
    contrast(roles["--mm-contrast-fg"], roles["--mm-contrast-bg"]),
    FLOOR.TEXT,
  );
  for (const role of ["--mm-danger", "--mm-success", "--mm-warning"]) {
    check(`${role} on page`, contrast(roles[role], roles["--mm-bg"]), FLOOR.TEXT);
  }
  for (const role of ["--mm-hero-from", "--mm-hero-to"]) {
    check(`${role} on page`, contrast(roles[role], roles["--mm-bg"]), FLOOR.HERO);
  }
  const surfaceStep = contrast(roles["--mm-surface"], roles["--mm-bg"]);
  const elevatedStep = contrast(roles["--mm-elevated"], roles["--mm-bg"]);
  if (surfaceStep <= 1.02) failures.push("surface does not step away from the page");
  if (elevatedStep <= surfaceStep) failures.push("elevated does not step above surface");
  return failures;
}
