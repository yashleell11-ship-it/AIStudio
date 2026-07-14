import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';

/// Type scale for the ManhwaManiacs "Eclipse Warm" theme.
///
/// Fonts are **bundled as assets** (see `pubspec.yaml` `fonts:`) and referenced
/// by family name — the app NEVER fetches fonts at runtime, so Settings (and
/// every other screen) can render offline or behind a network that blocks
/// fonts.gstatic.com without hanging or crashing.
///   • Display / large headings → **Syne** (geometric, characterful).
///   • Body / UI / everything else → **DM Sans**.
///   • Monospace → **Space Mono**.
///
/// Both Syne and DM Sans are shipped as single *variable* TTFs with a `wght`
/// axis, so the concrete weight is applied per-style via
/// [FontVariation]`('wght', …)` in addition to [TextStyle.fontWeight] (the
/// latter keeps synthetic weighting sane if the platform ever falls back).
///
/// Style NAMES and metrics (size / weight / height / spacing) are unchanged
/// from the previous scale so no screen breaks. Uppercase/tracking is applied
/// at call sites.
abstract final class AppTypography {
  static const String fontFamilyDisplay = 'Syne';
  static const String fontFamilyBody = 'DMSans';
  static const String fontFamilyMono = 'SpaceMono';

  static List<FontVariation> _wght(FontWeight? weight) =>
      [FontVariation('wght', (weight ?? FontWeight.w400).value.toDouble())];

  /// DM Sans base — used for body, headings h2..h4, labels, captions.
  static TextStyle _dm({
    double? fontSize,
    FontWeight? fontWeight,
    double? height,
    double? letterSpacing,
    Color? color,
  }) =>
      TextStyle(
        fontFamily: fontFamilyBody,
        leadingDistribution: TextLeadingDistribution.even,
        fontSize: fontSize,
        fontWeight: fontWeight,
        fontVariations: _wght(fontWeight),
        height: height ?? 1.5,
        letterSpacing: letterSpacing,
        color: color ?? AppColors.fg,
      );

  /// Syne — used for display styles and h1 (large, characterful headings).
  static TextStyle _syne({
    double? fontSize,
    FontWeight? fontWeight,
    double? height,
    double? letterSpacing,
    Color? color,
  }) =>
      TextStyle(
        fontFamily: fontFamilyDisplay,
        leadingDistribution: TextLeadingDistribution.even,
        fontSize: fontSize,
        fontWeight: fontWeight,
        fontVariations: _wght(fontWeight),
        height: height ?? 1.5,
        letterSpacing: letterSpacing,
        color: color ?? AppColors.fg,
      );

  // ── Display (Syne, large headings) ─────────────────────────────────────────
  static final TextStyle displayLg = _syne(
    fontSize: 48,
    fontWeight: FontWeight.w700,
    height: 1.1,
    letterSpacing: 1.5,
  );

  static final TextStyle displayMd = _syne(
    fontSize: 36,
    fontWeight: FontWeight.w700,
    height: 1.1,
    letterSpacing: 1,
  );

  // ── Headings ───────────────────────────────────────────────────────────────
  static final TextStyle h1 = _syne(
    fontSize: 28,
    fontWeight: FontWeight.w700,
    height: 1.2,
  );

  static final TextStyle h2 = _dm(
    fontSize: 22,
    fontWeight: FontWeight.w600,
    height: 1.3,
  );

  static final TextStyle h3 = _dm(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    height: 1.35,
  );

  static final TextStyle h4 = _dm(
    fontSize: 16,
    fontWeight: FontWeight.w600,
    height: 1.4,
  );

  // ── Body ───────────────────────────────────────────────────────────────────
  static final TextStyle bodyLg = _dm(
    fontSize: 16,
    fontWeight: FontWeight.w400,
  );

  static final TextStyle body = _dm(
    fontSize: 14,
    fontWeight: FontWeight.w400,
  );

  static final TextStyle bodySm = _dm(
    fontSize: 12,
    fontWeight: FontWeight.w400,
  );

  // ── UI / Labels ────────────────────────────────────────────────────────────
  static final TextStyle labelLg = _dm(
    fontSize: 14,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.1,
  );

  static final TextStyle label = _dm(
    fontSize: 12,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.1,
  );

  static final TextStyle labelSm = _dm(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.2,
  );

  // ── Captions / Badges ─────────────────────────────────────────────────────
  static final TextStyle caption = _dm(
    fontSize: 11,
    fontWeight: FontWeight.w400,
    color: AppColors.muted,
  );

  // ── Monospace ─────────────────────────────────────────────────────────────
  static const TextStyle mono = TextStyle(
    fontFamily: fontFamilyMono,
    leadingDistribution: TextLeadingDistribution.even,
    fontSize: 13,
    fontWeight: FontWeight.w400,
    height: 1.5,
    color: AppColors.fg,
  );

  // ── TextTheme for MaterialApp ──────────────────────────────────────────────
  static TextTheme get textTheme => TextTheme(
        displayLarge: h1,
        displayMedium: h2,
        displaySmall: h3,
        headlineMedium: h4,
        bodyLarge: bodyLg,
        bodyMedium: body,
        bodySmall: bodySm,
        labelLarge: labelLg,
        labelMedium: label,
        labelSmall: labelSm,
      );
}
