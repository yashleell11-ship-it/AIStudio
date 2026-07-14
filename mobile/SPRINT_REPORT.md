# ManhwaManiacs — Product Polish & Maturity Sprint Report

_Date: 2026-07-06 · Scope: Android app (`mobile/`) only — no backend, infra, deploy, or AI work._

## Summary

Two back-to-back sprints on the Flutter client: (1) a **UX polish** pass to make the app
_feel_ significantly better, and (2) a **maturity / reliability** pass. The codebase was already
well-architected (feature-first, Riverpod, go_router, a genuinely sophisticated reader, ~20.7k LOC
app + ~11.6k LOC tests), so the work focused on the high-signal details that separate a stock reader
from a premium one — tactile feedback, living loading states, smoother motion — plus a real bug fix
and de-duplication.

Every change was validated with a full Flutter toolchain (`dart analyze` + the complete
`flutter test` suite of **274 tests**).

## Validation results

| Check | Result |
|---|---|
| `dart analyze lib test` | **0 errors, 0 warnings** (258 pre-existing cosmetic infos; lib infos reduced 86 → 84) |
| `flutter test` (full suite) | **274 / 274 passing** |
| Pre-existing failures fixed | 1 (diagnostics screen overflow) |
| New issues introduced | 0 |
| Release APK | Not built in this environment (no Android SDK available here) — see "Building the APK" |

Test totals by area: reader 69 · downloads 46 · library 44 · settings 33 · sources 31 · core 21 ·
collections 13 · remaining-screens 8 · updates 6 · setup 2 · smoke 1.

## Files changed

### New files (3)
- `lib/core/utils/haptics.dart` — centralized, preference-gated haptic helper (`selection` / `light` / `medium`).
- `lib/shared/widgets/pressable.dart` — reusable press-in scale wrapper with long-press haptic.
- `lib/features/sources/utils/source_branding.dart` — shared source favicon map, `prettifySourceId`, and the `SourceLogo` widget (de-duplicated from the sources list).

### Modified files (12)
- `lib/features/reader/widgets/reader_content.dart` — haptics on every reader gesture; animated chapter edge-prompts; cross-fading page backdrop.
- `lib/shared/widgets/skeleton_box.dart` — static box → animated shimmer sweep; extracted reusable `ShimmerFill`.
- `lib/app/router/app_router.dart` — immersive fade transition when entering/leaving the reader.
- `lib/features/settings/screens/diagnostics_screen.dart` — **fixed RenderFlex overflow** in `_InfoRow`.
- `lib/features/settings/screens/settings_screen.dart` — new "Haptic feedback" toggle; hardened `_InfoRow` against overflow.
- `lib/features/settings/providers/settings_provider.dart` — `hapticFeedbackProvider` + `hapticsProvider`.
- `lib/core/storage/preferences.dart` — persisted `hapticFeedback` preference (default on).
- `lib/features/library/widgets/library/series_grid.dart` — library cover cards are now `Pressable`.
- `lib/features/sources/screens/source_browser_screen.dart` — dense cards `Pressable`; app bar shows the real source name + logo instead of the raw id.
- `lib/features/sources/screens/sources_list_screen.dart` — uses shared `SourceLogo`; removed duplicated favicon map; fixed import ordering.
- `lib/shared/widgets/series_cover_image.dart` — smooth fade-in + refined gradient placeholder.
- `lib/shared/widgets/stat_card.dart` — removed a redundant `dart:ui` import.

## UX improvements

- **Haptics across the app.** Page turns, chapter changes, double-tap zoom, lock/unlock, bookmark
  saves, auto-advance, favouriting and long-presses now give subtle, tasteful haptic feedback —
  the single biggest "feels premium" change. Fully user-controllable via a new **Settings →
  General → Haptic feedback** toggle (persisted, default on).
- **Living loading states.** Every skeleton in the app (library, downloads, collections, series
  detail, source browser, reader) now shimmers instead of sitting as a flat block.
- **Tactile cards.** Library and source cover cards scale in slightly on press, so taps feel
  physical rather than instantaneous.
- **Reader immersion.** Chapter edge-prompts fade + gently pop in instead of appearing abruptly;
  the page backdrop cross-fades when switching Dark/AMOLED/Paper; entering and leaving the reader
  now fades (like slipping into the page) rather than sliding laterally.
- **Source identity.** The source browser shows the real source name ("Toonily") and its logo in
  the app bar instead of the raw connector id ("toonily").
- **Covers.** Series covers fade in smoothly over a subtle gradient placeholder instead of popping.

## Performance improvements

- Skeleton shimmer is isolated in a `RepaintBoundary` and driven by a single lightweight
  `AnimatedBuilder`, so it never repaints siblings.
- The animated reader backdrop is a separate `Positioned.fill` layer, keeping the cross-fade off the
  virtualized page list (the reader's existing `ValueNotifier`-based no-rebuild scrolling is
  preserved untouched).
- `Pressable` only rebuilds its own subtree on press (local `setState`), never the surrounding grid.
- Removed a redundant import and a duplicated favicon lookup map (less code to load/parse).

## Bugs fixed

- **Diagnostics screen layout overflow (pre-existing).** `_InfoRow` rendered a fixed label + value
  in a `spaceBetween` Row with no flex — long device-info values overflowed by ~55px (yellow/black
  stripes) and the widget test failed. Fixed by making the value `Flexible` + right-aligned; applied
  the same hardening to the Settings → About `_InfoRow` to prevent the same class of bug there.

## Refactors / dead code

- Extracted the source favicon/branding logic into one shared module (`source_branding.dart`) and
  deleted the duplicated private copy in `sources_list_screen.dart`.
- Extracted a reusable `ShimmerFill` from `SkeletonBox` (used by both explicit skeletons and, where
  safe, other placeholders).
- Removed a redundant `dart:ui` import and fixed an out-of-order import directive.

## Reader specifics

The reader was already the strongest part of the app (virtualized list, prefetch, decode-at-display-
size, manual double-tap detection to avoid the 300ms delay, `ValueNotifier`-driven overlays).
This sprint added the finishing layer on top without disturbing that engine: haptics on every
interaction, animated edge-prompts, a cross-fading backdrop, and an immersive route transition. All
69 reader tests still pass.

## A deliberate non-change

`library_toolbar.dart` and `search_toolbar.dart` use the now-deprecated `DropdownButtonFormField
(value:)` and already carry `// ignore: deprecated_member_use`. Because that choice looks
intentional (SDK-compatibility), it was left as-is rather than force-migrated to `initialValue:`.
See recommendations.

## Building the APK

The release APK could not be built in this environment — it has the Flutter SDK but no Android SDK
(and installing the full Android toolchain here isn't feasible). Because the entire test suite
compiles and exercises every screen and passes, the code is build-ready. On your machine:

```
cd mobile
flutter pub get
flutter analyze
flutter test
flutter build apk --release        # or: --split-per-abi for smaller per-device APKs
```

Output: `mobile/build/app/outputs/flutter-apk/app-release.apk`.
(Note: `mobile/android/` contains a stale `hs_err_pid27580.log` JVM crash log from an earlier local
build — safe to delete.)

## Remaining opportunities / recommendations

1. **Fonts.** The design system declares `Inter`, `BebasNeue`, and `SpaceMono`, but no font files are
   bundled (no `fonts:` section in `pubspec.yaml`, no `.ttf` assets) — the app silently renders in
   Roboto. Bundling the intended fonts is the single highest-impact remaining visual upgrade.
2. **Cosmetic analyzer infos.** ~84 `info`-level lints remain in `lib` (mostly `prefer_const_constructors`
   and `avoid_redundant_argument_values`). `dart fix --apply` clears most safely — deferred here only
   to avoid noise in this sprint's diff.
3. **Deprecation.** If the project is firmly on Flutter ≥3.33, migrate the two `DropdownButtonFormField
   (value:)` toolbars to `initialValue:` and drop the ignore comments.
4. **Haptics reach.** Consider extending haptics to a few more confirmations (pull-to-refresh trigger,
   destructive-action confirms) for full consistency.
5. **Skeleton consolidation.** `collections_skeleton`, `downloads_skeleton`, `library_skeleton`, and
   `series_detail_skeleton` share structure and could be unified further.
