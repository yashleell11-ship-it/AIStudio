import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_palette.dart';

/// The curated theme registry — every palette the app can wear.
///
/// Values are adapted from proven colour systems (Nord, Dracula, Catppuccin,
/// Gruvbox, Tokyo Night, Rosé Pine, Everforest, Solarized) rather than
/// invented, then adjusted only where a token failed the WCAG floor the suite
/// enforces (`test/app/theme/palette_contrast_test.dart`): body text ≥ 4.5:1
/// on every surface, muted text ≥ 3:1, accents/semantics ≥ 3:1 on surfaces,
/// and on-colour text ≥ 4.5:1. Adjustments are noted inline so each system's
/// identity survives review.
abstract final class AppPalettes {
  /// The shipped "Eclipse Warm" look — unchanged, and the default.
  static const AppPalette eclipse = AppPalette(
    id: 'eclipse',
    name: 'Eclipse',
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

  /// Nord — polar night surfaces, frost accents. Muted text is brighter than
  /// nord3 (#4C566A ≈ 1.9:1, an infamous Nord readability trap) and the
  /// aurora red is lifted to #D0747E to clear 3:1 on nord1.
  static const AppPalette nord = AppPalette(
    id: 'nord',
    name: 'Nord',
    brightness: Brightness.dark,
    bg: Color(0xFF2E3440),
    surface: Color(0xFF3B4252),
    surface2: Color(0xFF434C5E),
    surfaceElevated: Color(0xFF434C5E),
    fg: Color(0xFFECEFF4),
    muted: Color(0xFFAEB8C9),
    primary: Color(0xFF88C0D0),
    primaryHover: Color(0xFF81A1C1),
    primaryFg: Color(0xFF2E3440),
    primarySoft: Color(0xFF8FBCBB),
    accent: Color(0xFF81A1C1),
    accentSoft: Color(0xFFB48EAD),
    accentFg: Color(0xFF2E3440),
    danger: Color(0xFFD0747E),
    success: Color(0xFFA3BE8C),
    warning: Color(0xFFEBCB8B),
  );

  /// Dracula — the classic purple/pink on near-navy. Comment blue-grey
  /// (#6272A4) fails 3:1, so muted uses a lifted #A8AFC7.
  static const AppPalette dracula = AppPalette(
    id: 'dracula',
    name: 'Dracula',
    brightness: Brightness.dark,
    bg: Color(0xFF282A36),
    surface: Color(0xFF303241),
    surface2: Color(0xFF3B3D4F),
    surfaceElevated: Color(0xFF3B3D4F),
    fg: Color(0xFFF8F8F2),
    muted: Color(0xFFA8AFC7),
    primary: Color(0xFFBD93F9),
    primaryHover: Color(0xFF9A6EE0),
    primaryFg: Color(0xFF1E1F29),
    primarySoft: Color(0xFFD6BCFA),
    accent: Color(0xFFFF79C6),
    accentSoft: Color(0xFF8BE9FD),
    accentFg: Color(0xFF1E1F29),
    danger: Color(0xFFFF5555),
    success: Color(0xFF50FA7B),
    warning: Color(0xFFF1FA8C),
  );

  /// Catppuccin Mocha — official base/surface0 ladder, mauve primary.
  static const AppPalette mocha = AppPalette(
    id: 'mocha',
    name: 'Catppuccin Mocha',
    brightness: Brightness.dark,
    bg: Color(0xFF1E1E2E),
    surface: Color(0xFF26263A),
    surface2: Color(0xFF313244),
    surfaceElevated: Color(0xFF313244),
    fg: Color(0xFFCDD6F4),
    muted: Color(0xFFA6ADC8),
    primary: Color(0xFFCBA6F7),
    primaryHover: Color(0xFFB4BEFE),
    primaryFg: Color(0xFF11111B),
    primarySoft: Color(0xFFF5C2E7),
    accent: Color(0xFF89B4FA),
    accentSoft: Color(0xFF94E2D5),
    accentFg: Color(0xFF11111B),
    danger: Color(0xFFF38BA8),
    success: Color(0xFFA6E3A1),
    warning: Color(0xFFF9E2AF),
  );

  /// Gruvbox Dark (hard) — retro warm oranges over brown-black.
  static const AppPalette gruvbox = AppPalette(
    id: 'gruvbox',
    name: 'Gruvbox',
    brightness: Brightness.dark,
    bg: Color(0xFF1D2021),
    surface: Color(0xFF282828),
    surface2: Color(0xFF32302F),
    surfaceElevated: Color(0xFF32302F),
    fg: Color(0xFFEBDBB2),
    muted: Color(0xFFA89984),
    primary: Color(0xFFFE8019),
    primaryHover: Color(0xFFD65D0E),
    primaryFg: Color(0xFF1D2021),
    primarySoft: Color(0xFFFABD2F),
    accent: Color(0xFF8EC07C),
    accentSoft: Color(0xFFFABD2F),
    accentFg: Color(0xFF1D2021),
    danger: Color(0xFFFB4934),
    success: Color(0xFFB8BB26),
    warning: Color(0xFFFABD2F),
  );

  /// Tokyo Night — indigo storm surfaces, blue/purple neon. Comment
  /// #565F89 fails 3:1, so muted uses the lifted #8F9BC0.
  static const AppPalette tokyoNight = AppPalette(
    id: 'tokyo_night',
    name: 'Tokyo Night',
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

  /// Rosé Pine — muted rose/iris over deep plum, gold keeps the Eclipse
  /// kinship (both use #F6C177).
  static const AppPalette rosePine = AppPalette(
    id: 'rose_pine',
    name: 'Rosé Pine',
    brightness: Brightness.dark,
    bg: Color(0xFF191724),
    surface: Color(0xFF1F1D2E),
    surface2: Color(0xFF26233A),
    surfaceElevated: Color(0xFF26233A),
    fg: Color(0xFFE0DEF4),
    muted: Color(0xFF908CAA),
    primary: Color(0xFFEBBCBA),
    primaryHover: Color(0xFFD7827E),
    primaryFg: Color(0xFF191724),
    primarySoft: Color(0xFFF6C177),
    accent: Color(0xFFC4A7E7),
    accentSoft: Color(0xFF9CCFD8),
    accentFg: Color(0xFF191724),
    danger: Color(0xFFEB6F92),
    success: Color(0xFF9CCFD8),
    warning: Color(0xFFF6C177),
  );

  /// Everforest Dark (medium) — soft green comfort palette, easy on the eyes
  /// for long reading sessions.
  static const AppPalette everforest = AppPalette(
    id: 'everforest',
    name: 'Everforest',
    brightness: Brightness.dark,
    bg: Color(0xFF272E33),
    surface: Color(0xFF2E383D),
    surface2: Color(0xFF374145),
    surfaceElevated: Color(0xFF374145),
    fg: Color(0xFFD3C6AA),
    muted: Color(0xFF9DA9A0),
    primary: Color(0xFFA7C080),
    primaryHover: Color(0xFF83C092),
    primaryFg: Color(0xFF272E33),
    primarySoft: Color(0xFFDBBC7F),
    accent: Color(0xFFE69875),
    accentSoft: Color(0xFF83C092),
    accentFg: Color(0xFF272E33),
    danger: Color(0xFFE67E80),
    success: Color(0xFFA7C080),
    warning: Color(0xFFDBBC7F),
  );

  /// Solarized Dark — base1 (#93A1A1 ladder) lifted slightly for the 4.5:1
  /// body floor; blue/cyan accents brightened the minimum needed for 3:1.
  static const AppPalette solarizedDark = AppPalette(
    id: 'solarized_dark',
    name: 'Solarized Dark',
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

  /// Catppuccin Latte — official base/mantle ladder; green and yellow
  /// darkened (as Catppuccin themselves do for badges) to clear 3:1, and the
  /// sky "soft" accent deepened to #0B7FA6 for the same reason.
  static const AppPalette latte = AppPalette(
    id: 'latte',
    name: 'Catppuccin Latte',
    brightness: Brightness.light,
    bg: Color(0xFFEFF1F5),
    surface: Color(0xFFFFFFFF),
    surface2: Color(0xFFE6E9EF),
    surfaceElevated: Color(0xFFFFFFFF),
    fg: Color(0xFF4C4F69),
    muted: Color(0xFF61647E),
    primary: Color(0xFF8839EF),
    primaryHover: Color(0xFF7287FD),
    primaryFg: Color(0xFFFFFFFF),
    primarySoft: Color(0xFF7C3AED),
    accent: Color(0xFF1E66F5),
    accentSoft: Color(0xFF0B7FA6),
    accentFg: Color(0xFFFFFFFF),
    danger: Color(0xFFD20F39),
    success: Color(0xFF358A22),
    warning: Color(0xFFAE6F0F),
  );

  /// Rosé Pine Dawn — rose and iris deepened just past their official values
  /// (#B4637A → #A65468, #907AA9 → #7E6699) so light text on filled buttons
  /// clears 4.5:1; gold darkened for the 3:1 floor.
  static const AppPalette dawn = AppPalette(
    id: 'dawn',
    name: 'Rosé Pine Dawn',
    brightness: Brightness.light,
    bg: Color(0xFFFAF4ED),
    surface: Color(0xFFFFFAF3),
    surface2: Color(0xFFF2E9E1),
    surfaceElevated: Color(0xFFFFFAF3),
    fg: Color(0xFF464261),
    muted: Color(0xFF6E6A86),
    primary: Color(0xFFA65468),
    primaryHover: Color(0xFF8E4758),
    primaryFg: Color(0xFFFFFAF3),
    primarySoft: Color(0xFF9E5065),
    accent: Color(0xFF7E6699),
    accentSoft: Color(0xFF56949F),
    accentFg: Color(0xFFFFFAF3),
    danger: Color(0xFFB4433A),
    success: Color(0xFF286983),
    warning: Color(0xFFA96A1C),
  );

  /// Solarized Light — cream base3/base2 ladder; blue/cyan/semantics
  /// deepened the minimum needed for the floors.
  static const AppPalette solarizedLight = AppPalette(
    id: 'solarized_light',
    name: 'Solarized Light',
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

  /// Gallery order: default first, then darks, then lights.
  static const List<AppPalette> all = [
    eclipse,
    amoled,
    nord,
    dracula,
    mocha,
    gruvbox,
    tokyoNight,
    rosePine,
    everforest,
    solarizedDark,
    daylight,
    paper,
    latte,
    dawn,
    solarizedLight,
  ];

  static List<AppPalette> get darkPalettes =>
      all.where((p) => p.isDark).toList(growable: false);

  static List<AppPalette> get lightPalettes =>
      all.where((p) => !p.isDark).toList(growable: false);

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
