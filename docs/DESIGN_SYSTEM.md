# ManhwaManiacs — Eclipse Warm Design System (redesign contract)

Single source of truth for the 0→100 redesign. **Web hex == mobile hex.** Token
*names* are stable; only their *values* changed to Eclipse Warm. Build on these
names — do not hard-code hex in components.

## Palette (Eclipse Warm)

| Role | Hex | Web token / util | Mobile (`AppColors`) |
|------|-----|------------------|----------------------|
| Void bg (html/body/root) | `#0A0A0A` | `bg-bg`, `--color-bg-void` | `bg`, `bgVoid` |
| Surface (cards/panels) | `#111111` | `bg-surface`, `--color-bg-surface` | `surface`/`panel`, `bgSurface` |
| Elevated (modals/sheets) | `#181818` | `bg-surface-2`, `--color-bg-elevated` | `surface2`/`surfaceElevated`, `bgElevated` |
| Light contrast section | `#FFFFFF` | `bg-bg-light` | `bgLight` |
| Text primary (on dark) | `#DDE4EA` | `text-fg`, `--color-text-primary` | `fg` |
| Text muted | `#9AA8B4` | `text-muted` | `muted` |
| Text dark (on white) | `#0C0C0C` | `text-text-dark` | `textDark` |
| Accent amber (active nav, progress, highlights) | `#F59E0B` | `text-primary`/`bg-primary`, `--color-accent-amber` | `primary`, `accentAmber` |
| Accent rose (CTA gradient end / accent) | `#BE4C00` | `bg-accent`, `--color-accent-rose` | `accent`, `accentRose` |
| Accent warm (hover) | `#C2410C` | `--color-accent-warm`, `bg-primary-hover` | `accentWarm`, `primaryHover` |
| Border subtle | `rgba(221,228,234,0.12)` | `border-border`, `--color-border-subtle` | `border`, `borderSubtle` |
| Border on light | `rgba(12,12,12,0.12)` | `--color-border-light` | `borderLight` |
| danger / success / warning | `#EF4444` / `#10B981` / `#F59E0B` | `bg-danger`… | `danger`/`success`/`warning` |

Legacy `violet-*`/`cyan-*` tokens still exist but are repointed to warm
(amber/rose) so any stray usage reads warm — **prefer the semantic names above**
and remove violet/cyan class usages when you touch a file.

## Typography

- **Display:** Syne (400–800). Web: `font-display` / `var(--font-syne)`. Mobile: `GoogleFonts.syne` (used by `AppTypography.displayLg/displayMd/h1`).
- **Body/UI:** DM Sans (300–600). Web: `font-sans` / `var(--font-dm-sans)` (default). Mobile: `GoogleFonts.dmSans` (all other `AppTypography.*`).
- **Nav labels:** uppercase, `tracking-widest`, `font-medium`.
- **Hero headings:** `.hero-heading` (bronze→cream gradient text), uppercase, `font-black`, tight tracking, `leading-none`. Mobile: `HeroHeading` widget (see premium).

## Gradients & effects (web utilities, in `globals.css`)

- `.hero-heading` — `linear-gradient(180deg,#9A8B7A,#E8DFD0)` clipped to text.
- `.cta-gradient` — `linear-gradient(123deg,#1A0A00 7%,#BE4C00 37%,#C2410C 72%,#F59E0B 100%)` + inset warm glow + `outline:2px solid white; outline-offset:-3px`. Used by `PrimaryPillButton`.
- `.glass-panel` / `.glass-card` — warm dark tint + `backdrop-blur`.
- `--shadow-glow` — `0 0 24px rgba(245,158,11,0.22)`.

## Radius

- Web: `rounded-sm/md/lg`, `rounded-xl`(1.5rem), `rounded-3xl`(40px), `rounded-4xl`(60px). Pills: `rounded-full`. Section tops: `rounded-t-[40px] sm:rounded-t-[50px] md:rounded-t-[60px]`.
- Mobile (`AppRadius`, in `app_spacing.dart`): `xs4 sm6 md10 lg14 xl20 xl2:28 xl3:40 xl4:60 pill:999 full:9999`.

## Premium primitives (build in Wave 2; pages import these)

Web — `frontend/src/components/premium/`:
`FadeIn`, `Magnet`, `AnimatedText`, `ScrollMarquee`, `StickyStack`,
`PrimaryPillButton` (default label "Continue Reading", `.cta-gradient`),
`GhostPillButton` (`border-2 border-fg`, uppercase, hover `bg-fg/10`),
`ContrastSection` (white rounded-top), `HeroHeading`, `GlassPanel`.
Reduced motion via `use-prefers-reduced-motion` hook — all motion primitives must honor it. `framer-motion@^12` is installed.

Mobile — `mobile/lib/shared/widgets/premium/`:
`fade_in.dart`, `magnet.dart`, `primary_pill_button.dart`, `ghost_pill_button.dart`,
`scroll_marquee.dart`, `sticky_stack.dart`, `hero_heading.dart`, `glass_panel.dart`.
Honor `MediaQuery.disableAnimationsOf(context)`. Mirror web visuals/naming.

## Motion specs (summary — see master prompt §2.7)

- **FadeIn:** `whileInView`, `viewport={{once:true,margin:"50px"}}`, `y:30`, `duration:0.7`, ease `[0.25,0.1,0.25,1]`; props `delay/x/y`.
- **Magnet:** mouse-follow translate3d, `padding:150`, `strength:3`, active `transform .3s ease-out` / idle `.6s ease-in-out`, `willChange:transform`.
- **ScrollMarquee:** offset `(scrollY - sectionTop + innerHeight)*0.3`; row1 `translateX(offset-200)`, row2 `translateX(-(offset-200))`; passive listener; tiles 420×270 `rounded-2xl object-cover` lazy; triple the array for seamless loop.
- **AnimatedText:** per-char opacity 0.2→1, `useScroll` offset `['start 0.8','end 0.2']`.
- **StickyStack:** `targetScale = 1 - (total-1-index)*0.03`, sticky `top-24 md:top-32`, container `h-[85vh]`, card offset `top:index*28px`.
- **Reduced motion:** disable marquee parallax, magnet, char animation, sticky scale.

## Hard constraints (do not break)

Profile picker on every cold start (~5s mood animation); Library tab (mobile) =
followed series only; reading history in Settings; sources grid = logo+name only;
reader settings sheet swipe-down dismiss (mobile); mature toggle / admin / auth
intact; **backend API unchanged**; keep reader virtual scrolling & scroll restore.
Do not rename the app. Do not commit git.
