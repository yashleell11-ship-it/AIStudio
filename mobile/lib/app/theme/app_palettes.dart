import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_palette.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.generated.dart';

/// The theme registry — every palette the app can wear.
///
/// Two kinds live here.
///
/// **House palettes**, written by hand and declared below: Eclipse (the
/// default, and the app's own look), its OLED twin, Daylight, Paper, and the
/// three systems the base16 corpus has no shippable equivalent for — Tokyo
/// Night, Solarized Dark and Solarized Light.
///
/// **base16 palettes**, in [Base16Palettes], converted by
/// `tool/themes/build_palettes.dart` from the exact set the web app ships, so
/// a scheme called Kanagawa wears the same colours in both places. Eight of
/// them (Nord, Dracula, Catppuccin Mocha, Gruvbox Hard, Rosé Pine, Everforest,
/// Catppuccin Latte, Rosé Pine Dawn) replaced hand-written palettes of the
/// same name and inherited their ids, so a stored preference keeps naming the
/// theme it always named.
///
/// Every palette in [all], generated or not, clears the WCAG floors the suite
/// enforces (`test/app/theme/palette_contrast_test.dart`): body text ≥ 4.5:1
/// on every surface, muted text ≥ 3:1, accents/semantics ≥ 3:1 on surfaces,
/// and on-colour text ≥ 4.5:1. Hand-written adjustments are noted inline so
/// each system's identity survives review; generated ones carry their worst
/// measured pairing in the doc comment.
abstract final class AppPalettes {
  /// The shipped "Eclipse Warm" look — unchanged, and the default.
  static const AppPalette eclipse = AppPalette(
    id: 'eclipse',
    name: 'Eclipse',
    description: 'Amber on near-black — the house look.',
    brightness: Brightness.dark,
    bg: Color(0xFF0A0A0A),
    surface: Color(0xFF111111),
    surface2: Color(0xFF181818),
    surfaceElevated: Color(0xFF181818),
    fg: Color(0xFFDDE4EA),
    muted: Color(0xFF9AA8B4),
    primary: Color(0xFFF59E0B),
    primaryHover: Color(0xFFC2410C),
    primaryFg: Color(0xFF0C0C0C),
    primarySoft: Color(0xFFF6C177),
    accent: Color(0xFFBE4C00),
    accentSoft: Color(0xFFF6C177),
    accentFg: Color(0xFFFFFFFF),
    danger: Color(0xFFEF4444),
    success: Color(0xFF10B981),
    warning: Color(0xFFF59E0B),
  );

  /// True-black Eclipse for OLED panels — the ember accent kept at the
  /// Eclipse value (#BE4C00) so white-on-accent stays ≥ 4.5:1.
  static const AppPalette amoled = AppPalette(
    id: 'amoled',
    name: 'Midnight OLED',
    description: 'Eclipse on true black, for panels that switch pixels off.',
    brightness: Brightness.dark,
    bg: Color(0xFF000000),
    surface: Color(0xFF0A0A0A),
    surface2: Color(0xFF141414),
    surfaceElevated: Color(0xFF141414),
    fg: Color(0xFFE6EAEE),
    muted: Color(0xFF9CA8B2),
    primary: Color(0xFFF59E0B),
    primaryHover: Color(0xFFC2410C),
    primaryFg: Color(0xFF0C0C0C),
    primarySoft: Color(0xFFF6C177),
    accent: Color(0xFFBE4C00),
    accentSoft: Color(0xFFF6C177),
    accentFg: Color(0xFFFFFFFF),
    danger: Color(0xFFF05045),
    success: Color(0xFF12C48D),
    warning: Color(0xFFF5A623),
  );

  /// Tokyo Night — indigo storm surfaces, blue/purple neon. Comment
  /// #565F89 fails 3:1, so muted uses the lifted #8F9BC0.
  static const AppPalette tokyoNight = AppPalette(
    id: 'tokyo_night',
    name: 'Tokyo Night',
    description: 'Neon blue and violet over an indigo storm.',
    author: 'enkia',
    brightness: Brightness.dark,
    bg: Color(0xFF1A1B26),
    surface: Color(0xFF20222F),
    surface2: Color(0xFF292E42),
    surfaceElevated: Color(0xFF292E42),
    fg: Color(0xFFC0CAF5),
    muted: Color(0xFF8F9BC0),
    primary: Color(0xFF7AA2F7),
    primaryHover: Color(0xFF3D59A1),
    primaryFg: Color(0xFF15161E),
    primarySoft: Color(0xFF7DCFFF),
    accent: Color(0xFFBB9AF7),
    accentSoft: Color(0xFF7DCFFF),
    accentFg: Color(0xFF15161E),
    danger: Color(0xFFF7768E),
    success: Color(0xFF9ECE6A),
    warning: Color(0xFFE0AF68),
  );

  /// Solarized Dark — base1 (#93A1A1 ladder) lifted slightly for the 4.5:1
  /// body floor; blue/cyan accents brightened the minimum needed for 3:1.
  static const AppPalette solarizedDark = AppPalette(
    id: 'solarized_dark',
    name: 'Solarized Dark',
    description: 'The 2011 original, on its deep teal ground.',
    author: 'Ethan Schoonover',
    brightness: Brightness.dark,
    bg: Color(0xFF002B36),
    surface: Color(0xFF073642),
    surface2: Color(0xFF0E4250),
    surfaceElevated: Color(0xFF0E4250),
    fg: Color(0xFF9FB1B1),
    muted: Color(0xFF7E9498),
    primary: Color(0xFF41A0E4),
    primaryHover: Color(0xFF268BD2),
    primaryFg: Color(0xFF002B36),
    primarySoft: Color(0xFF6BC1E8),
    accent: Color(0xFF2AA198),
    accentSoft: Color(0xFF35C9BE),
    accentFg: Color(0xFF002B36),
    danger: Color(0xFFE4544F),
    success: Color(0xFF8A9F00),
    warning: Color(0xFFC29B0C),
  );

  // ── Light ────────────────────────────────────────────────────────────────

  /// Clean neutral light theme that keeps the brand's warm amber family,
  /// darkened (amber-700/800) to hold 3:1 on white.
  static const AppPalette daylight = AppPalette(
    id: 'daylight',
    name: 'Daylight',
    description: 'Neutral white with the house amber, darkened for paper.',
    brightness: Brightness.light,
    bg: Color(0xFFF7F7F8),
    surface: Color(0xFFFFFFFF),
    surface2: Color(0xFFEFF1F3),
    surfaceElevated: Color(0xFFFFFFFF),
    fg: Color(0xFF1B1F24),
    muted: Color(0xFF5A6470),
    primary: Color(0xFFB45309),
    primaryHover: Color(0xFF92400E),
    primaryFg: Color(0xFFFFFFFF),
    primarySoft: Color(0xFF92400E),
    accent: Color(0xFF9A3412),
    accentSoft: Color(0xFFB45309),
    accentFg: Color(0xFFFFFFFF),
    danger: Color(0xFFDC2626),
    success: Color(0xFF047857),
    warning: Color(0xFFB45309),
  );

  /// Warm paper/sepia — the classic long-form reading surface.
  static const AppPalette paper = AppPalette(
    id: 'paper',
    name: 'Paper',
    description: 'Warm sepia — the classic long-form reading surface.',
    brightness: Brightness.light,
    bg: Color(0xFFF3EAD7),
    surface: Color(0xFFFAF3E3),
    surface2: Color(0xFFEADFC8),
    surfaceElevated: Color(0xFFFAF3E3),
    fg: Color(0xFF3A2F1D),
    muted: Color(0xFF6F6046),
    primary: Color(0xFF8A5A1C),
    primaryHover: Color(0xFF6E4715),
    primaryFg: Color(0xFFFFF9EC),
    primarySoft: Color(0xFF6E4715),
    accent: Color(0xFF9C4221),
    accentSoft: Color(0xFF8A5A1C),
    accentFg: Color(0xFFFFF9EC),
    danger: Color(0xFFB3372F),
    success: Color(0xFF3E6B47),
    warning: Color(0xFF8F5F12),
  );

  /// Solarized Light — cream base3/base2 ladder; blue/cyan/semantics
  /// deepened the minimum needed for the floors.
  static const AppPalette solarizedLight = AppPalette(
    id: 'solarized_light',
    name: 'Solarized Light',
    description: 'The original at full brightness, on cream.',
    author: 'Ethan Schoonover',
    brightness: Brightness.light,
    bg: Color(0xFFFDF6E3),
    surface: Color(0xFFF7EFDA),
    surface2: Color(0xFFEEE8D5),
    surfaceElevated: Color(0xFFF7EFDA),
    fg: Color(0xFF49606A),
    muted: Color(0xFF62777C),
    primary: Color(0xFF176DA9),
    primaryHover: Color(0xFF135C8F),
    primaryFg: Color(0xFFFDF6E3),
    primarySoft: Color(0xFF16608F),
    accent: Color(0xFF187970),
    accentSoft: Color(0xFF176DA9),
    accentFg: Color(0xFFFDF6E3),
    danger: Color(0xFFC0322F),
    success: Color(0xFF577A00),
    warning: Color(0xFF8F6E00),
  );

  /// Every dark palette, house first, then the base16 set in the order the
  /// web curates it — which keeps families adjacent (every Gruvbox beside
  /// every other) instead of alphabetising them apart.
  static const List<AppPalette> darkPalettes = [
    eclipse,
    amoled,
    tokyoNight,
    solarizedDark,
    ...Base16Palettes.dark,
  ];

  /// Every light palette, same rule.
  static const List<AppPalette> lightPalettes = [
    daylight,
    paper,
    solarizedLight,
    ...Base16Palettes.light,
  ];

  /// Gallery order: darks then lights, the default first in both senses.
  static const List<AppPalette> all = [...darkPalettes, ...lightPalettes];

  /// The palettes this app drew itself, as opposed to the ones it borrowed.
  /// The gallery leads each section with them; they are also the ones whose
  /// look is the app's to change.
  static const List<AppPalette> house = [
    eclipse,
    amoled,
    tokyoNight,
    solarizedDark,
    daylight,
    paper,
    solarizedLight,
  ];

  /// Resolve a persisted id; unknown/absent ids fall back to [eclipse] so a
  /// removed palette can never brick startup.
  static AppPalette byId(String? id) {
    for (final palette in all) {
      if (palette.id == id) return palette;
    }
    return eclipse;
  }
}

/// The way widgets read the active palette: `context.colors.primary`.
///
/// Reading through [Theme.of] registers a dependency, so a palette switch
/// rebuilds every widget that painted with it. The fallback keeps widget
/// tests that pump a bare `MaterialApp(theme: ThemeData(...))` working.
extension AppPaletteContext on BuildContext {
  AppPalette get colors =>
      Theme.of(this).extension<AppPalette>() ?? AppPalettes.eclipse;
}
