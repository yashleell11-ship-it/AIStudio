# Design presets: change the whole look, not just the colours (1f)

**Date:** 2026-09-05
**Status:** Design — build-through.
**Branch:** `feat/vps-slim-source-native`.

## 1. What the owner asked for

> "also add change design fully in the app setting and then it ask for restart the app and
> everything of the app chages i mean ui the viewong experiance"

A setting that changes the **entire interface and reading experience**, not the palette.
Themes (base16, ~35 of them) already answer "what colour is it". This answers "what shape
is it" — density, surfaces, typography scale, how a library is laid out, how much chrome
the reader shows.

The two are **orthogonal and both persist**: Nord + Compact is a valid combination, as is
Nord + Editorial. A preset must never hard-code a colour, and a theme must never hard-code
a spacing.

## 2. The presets

Five, each a coherent position rather than a slider setting. Names are provisional; the
implementer may improve them.

| Preset | Character |
|---|---|
| **Eclipse** (default) | Exactly today's app: glass panels, translucency, generous spacing, poster-led browse. Must remain byte-identical — this is what the owner uses daily. |
| **Flat** | No translucency or blur. Solid surfaces, crisp hairline borders, the same density. Faster to paint, calmer, reads as a tool rather than a showcase. |
| **Compact** | Density-first: tighter spacing scale, smaller type step, more rows per screen, list-led browse instead of large covers. For scanning a big library. |
| **Editorial** | Typography-led: serif headings, wide margins, restrained accents, metadata over artwork. Pairs naturally with novels but applies app-wide. |
| **Cinema** | Content-maximal: chrome recedes, controls auto-hide, covers and pages get the screen. For reading, not managing. |

## 3. What a preset actually controls

A preset is a token bundle, sibling to the theme's colour bundle:

- **Spacing scale** (the app's `AppSpacing` / spacing tokens) — one multiplier is not enough;
  presets differ in rhythm, not just size.
- **Corner radius** and **border weight**.
- **Surface treatment** — glass/translucent vs solid vs bordered. This is the single most
  visible axis.
- **Typography scale and family role** — size steps, line height, and whether headings are
  sans or serif.
- **Layout defaults** — poster grid vs list vs compact rows for browse and library; how much
  metadata a card shows.
- **Motion** — how much animation; Cinema and Flat want less than Eclipse.
- **Reader chrome** — how much furniture the reader shows by default.

It controls **no colours at all**. Colour is the theme's job.

## 4. Applying it

**Apply live. Do not require a restart.** The owner expected one ("then it ask for restart"),
which is a fair assumption, but both clients can rebuild their widget/component trees from
changed tokens without one — and a restart that loses your place in a chapter is a worse
experience than the one it replaces.

Where something genuinely cannot hot-swap, prompt for a restart **for that case only**, and
say what needs it. Never a blanket "restart to apply".

## 5. Constraints

- **Eclipse must be byte-identical to today.** The regression bar: with Eclipse selected the
  app the owner uses daily is unchanged, pixel for pixel.
- **Presets are per profile**, like themes — the same persistence pattern.
- **Contrast still holds.** A preset changes weights and sizes; it must not push any
  text/background pairing below the WCAG floors the theme tests already enforce (body 4.5:1,
  muted 3:1). If a preset's smaller type step endangers a pairing, the preset is wrong.
- **The novel reader's twelve reading palettes stay separate.** Page surfaces for prose are a
  third, independent axis and are not touched here.
- Web and mobile ship the same five presets, so the two feel like one product.
