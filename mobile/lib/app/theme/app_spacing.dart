/// The base spacing scale — Tailwind's default steps (4px base unit).
///
/// Widgets do **not** read this directly any more: they read
/// `context.space.<step>`, which resolves through the active design preset
/// so density follows the preset the way colour follows the theme. What
/// lives here is the *shipped* rhythm, and `AppPresets.signature` is built
/// from these very constants so the default preset and this scale cannot
/// drift apart.
///
/// Two kinds of call site still read it directly, both deliberately: layout
/// math that has to be known outside a build (a `SliverPersistentHeader`
/// extent) and the reader's scroll geometry, where the padding constant and
/// the offset arithmetic must agree exactly or every page lands in the
/// wrong place.
abstract final class AppSpacing {
  static const double xxs = 2;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xl2 = 24;
  static const double xl3 = 32;
  static const double xl4 = 40;
  static const double xl5 = 48;
  static const double xl6 = 64;
  static const double xl7 = 80;
}

/// The base corner-radius scale — pills plus large soft cards.
///
/// As with [AppSpacing], widgets read `context.radii.<step>` so corners
/// follow the active preset; these constants are the shipped values that
/// `AppPresets.signature` is built from.
abstract final class AppRadius {
  static const double xs = 4;
  static const double sm = 6;
  static const double md = 10;
  static const double lg = 14;
  static const double xl = 20;
  static const double xl2 = 28;

  /// Large card radius (40px) — matches web large-card intent.
  static const double xl3 = 40;

  /// Extra-large hero/card radius (60px).
  static const double xl4 = 60;

  /// Fully rounded pill (999) — buttons, chips, tags.
  static const double pill = 999;
  static const double full = 9999;
}
