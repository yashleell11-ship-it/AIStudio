import 'package:flutter/material.dart';

/// One complete app colour scheme — every token a screen may paint with.
///
/// A palette is registered on [ThemeData] as a [ThemeExtension] so that every
/// `context.colors.…` read registers a Theme dependency: when the active
/// palette changes, exactly the widgets that read colours rebuild (and
/// [AnimatedTheme] cross-fades them via [lerp]). This — not a static lookup —
/// is what makes runtime theme switching repaint the whole app reliably.
///
/// The token set is the one the app actually consumes (censused from the old
/// static `AppColors` usages). Historical token NAMES (violet*/cyan*/panel/…)
/// are preserved as alias getters so existing call sites migrate mechanically.
@immutable
class AppPalette extends ThemeExtension<AppPalette> {
  const AppPalette({
    required this.id,
    required this.name,
    this.description = '',
    this.author = '',
    required this.brightness,
    required this.bg,
    required this.surface,
    required this.surface2,
    required this.surfaceElevated,
    required this.fg,
    required this.muted,
    required this.primary,
    required this.primaryHover,
    required this.primaryFg,
    required this.primarySoft,
    required this.accent,
    required this.accentSoft,
    required this.accentFg,
    required this.danger,
    required this.success,
    required this.warning,
  });

  /// Stable identifier persisted in preferences — never rename a shipped id.
  final String id;

  /// Human-readable name shown in the theme gallery.
  final String name;

  /// One line under the name in the gallery — what the palette looks like,
  /// not where it came from. Empty for the house palettes, which need no
  /// introduction on a picker the owner opens every day.
  final String description;

  /// Who made the scheme. Forty of these are community work lifted from
  /// `tinted-theming/schemes`; a picker that shows their colours and not
  /// their names is helping itself to them.
  final String author;

  /// Drives Material defaults and system status/nav-bar icon brightness.
  final Brightness brightness;

  // ── Core tokens ──────────────────────────────────────────────────────────
  final Color bg;
  final Color surface;
  final Color surface2;
  final Color surfaceElevated;
  final Color fg;
  final Color muted;
  final Color primary;
  final Color primaryHover;
  final Color primaryFg;

  /// Brighter/softer tint of the primary family — small text accents, ticks.
  final Color primarySoft;
  final Color accent;

  /// Softer companion to [accent] — secondary decorative highlights.
  final Color accentSoft;
  final Color accentFg;
  final Color danger;
  final Color success;
  final Color warning;

  bool get isDark => brightness == Brightness.dark;

  // ── Derived tokens ───────────────────────────────────────────────────────
  // Derived (not stored) so every palette keeps the same relationships the
  // Eclipse look established: hairline borders are ~12% foreground, glass
  // edges ~10%, glows are low-alpha washes of their base colour.
  Color get border => fg.withValues(alpha: 0.12);
  Color get glassEdge => fg.withValues(alpha: 0.10);
  Color get violetGlow => primary.withValues(alpha: 0.20);
  Color get cyanGlow => accent.withValues(alpha: 0.13);

  /// Modal barrier / overlay scrim — stays dark on every palette (it sits
  /// over content, not over theme surfaces).
  Color get scrim => const Color(0xCC000000);

  // ── Historical aliases (old AppColors names) ─────────────────────────────
  Color get panel => surface;
  Color get sidebar => surface;
  Color get abyss => bg;
  Color get void_ => surface;
  Color get violet300 => primarySoft;
  Color get violet400 => primarySoft;
  Color get violet500 => primary;
  Color get violet600 => primaryHover;
  Color get cyan400 => accentSoft;
  Color get cyan500 => accent;
  Color get amber400 => warning;
  Color get emerald400 => success;
  Color get rose400 => accent;
  Color get accentAmber => primary;
  Color get accentRose => accent;
  Color get bgVoid => bg;
  Color get bgSurface => surface;
  Color get bgElevated => surfaceElevated;
  Color get borderSubtle => border;

  @override
  AppPalette copyWith({
    String? id,
    String? name,
    String? description,
    String? author,
    Brightness? brightness,
    Color? bg,
    Color? surface,
    Color? surface2,
    Color? surfaceElevated,
    Color? fg,
    Color? muted,
    Color? primary,
    Color? primaryHover,
    Color? primaryFg,
    Color? primarySoft,
    Color? accent,
    Color? accentSoft,
    Color? accentFg,
    Color? danger,
    Color? success,
    Color? warning,
  }) {
    return AppPalette(
      id: id ?? this.id,
      name: name ?? this.name,
      description: description ?? this.description,
      author: author ?? this.author,
      brightness: brightness ?? this.brightness,
      bg: bg ?? this.bg,
      surface: surface ?? this.surface,
      surface2: surface2 ?? this.surface2,
      surfaceElevated: surfaceElevated ?? this.surfaceElevated,
      fg: fg ?? this.fg,
      muted: muted ?? this.muted,
      primary: primary ?? this.primary,
      primaryHover: primaryHover ?? this.primaryHover,
      primaryFg: primaryFg ?? this.primaryFg,
      primarySoft: primarySoft ?? this.primarySoft,
      accent: accent ?? this.accent,
      accentSoft: accentSoft ?? this.accentSoft,
      accentFg: accentFg ?? this.accentFg,
      danger: danger ?? this.danger,
      success: success ?? this.success,
      warning: warning ?? this.warning,
    );
  }

  @override
  AppPalette lerp(ThemeExtension<AppPalette>? other, double t) {
    if (other is! AppPalette) return this;
    // Identity (id/name/credit/brightness) snaps at the midpoint — only
    // colours fade, which is what AnimatedTheme animates during a switch.
    final target = t < 0.5 ? this : other;
    Color l(Color a, Color b) => Color.lerp(a, b, t)!;
    return AppPalette(
      id: target.id,
      name: target.name,
      description: target.description,
      author: target.author,
      brightness: target.brightness,
      bg: l(bg, other.bg),
      surface: l(surface, other.surface),
      surface2: l(surface2, other.surface2),
      surfaceElevated: l(surfaceElevated, other.surfaceElevated),
      fg: l(fg, other.fg),
      muted: l(muted, other.muted),
      primary: l(primary, other.primary),
      primaryHover: l(primaryHover, other.primaryHover),
      primaryFg: l(primaryFg, other.primaryFg),
      primarySoft: l(primarySoft, other.primarySoft),
      accent: l(accent, other.accent),
      accentSoft: l(accentSoft, other.accentSoft),
      accentFg: l(accentFg, other.accentFg),
      danger: l(danger, other.danger),
      success: l(success, other.success),
      warning: l(warning, other.warning),
    );
  }
}
