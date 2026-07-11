import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';

/// Type scale matching the ManhwaManiacs v2 frontend (Inter sans-serif).
///
/// Flutter ships with Roboto; Inter is loaded via pubspec assets if added later.
/// The size/weight mapping mirrors the Tailwind prose scale used in the desktop UI.
abstract final class AppTypography {
  static const TextStyle _base = TextStyle(
    fontFamily: 'Inter',
    color: AppColors.fg,
    height: 1.5,
    leadingDistribution: TextLeadingDistribution.even,
  );

  // ── Display (Bebas-like, large headings) ───────────────────────────────────
  static final TextStyle displayLg = _base.copyWith(
    fontFamily: 'BebasNeue',
    fontSize: 48,
    fontWeight: FontWeight.w700,
    height: 1.1,
    letterSpacing: 1.5,
  );

  static final TextStyle displayMd = _base.copyWith(
    fontFamily: 'BebasNeue',
    fontSize: 36,
    fontWeight: FontWeight.w700,
    height: 1.1,
    letterSpacing: 1,
  );

  // ── Headings ───────────────────────────────────────────────────────────────
  static final TextStyle h1 = _base.copyWith(
    fontSize: 28,
    fontWeight: FontWeight.w700,
    height: 1.2,
  );

  static final TextStyle h2 = _base.copyWith(
    fontSize: 22,
    fontWeight: FontWeight.w600,
    height: 1.3,
  );

  static final TextStyle h3 = _base.copyWith(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    height: 1.35,
  );

  static final TextStyle h4 = _base.copyWith(
    fontSize: 16,
    fontWeight: FontWeight.w600,
    height: 1.4,
  );

  // ── Body ───────────────────────────────────────────────────────────────────
  static final TextStyle bodyLg = _base.copyWith(
    fontSize: 16,
    fontWeight: FontWeight.w400,
  );

  static final TextStyle body = _base.copyWith(
    fontSize: 14,
    fontWeight: FontWeight.w400,
  );

  static final TextStyle bodySm = _base.copyWith(
    fontSize: 12,
    fontWeight: FontWeight.w400,
  );

  // ── UI / Labels ────────────────────────────────────────────────────────────
  static final TextStyle labelLg = _base.copyWith(
    fontSize: 14,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.1,
  );

  static final TextStyle label = _base.copyWith(
    fontSize: 12,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.1,
  );

  static final TextStyle labelSm = _base.copyWith(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.2,
  );

  // ── Captions / Badges ─────────────────────────────────────────────────────
  static final TextStyle caption = _base.copyWith(
    fontSize: 11,
    fontWeight: FontWeight.w400,
    color: AppColors.muted,
  );

  // ── Monospace ─────────────────────────────────────────────────────────────
  static final TextStyle mono = _base.copyWith(
    fontFamily: 'SpaceMono',
    fontSize: 13,
    fontWeight: FontWeight.w400,
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
